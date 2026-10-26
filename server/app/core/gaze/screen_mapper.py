"""Polynomial-regression mapping from eye features to normalised screen points.

A ridge-regularised quadratic regression from the six-value feature vector to
screen X and Y, fitted on samples from the multi-point calibration. Outputs are
fractions of the screen (0..1), so a profile survives resolution/DPI changes.

The expansion includes head-rotation cross terms. The eye-in-socket ratio only
describes gaze relative to the head; without them the mapping is only valid
while the head stays exactly where it was during calibration.
"""

import numpy as np

from app.core.gaze.feature_sources import (
    IRIS_FEATURE_SOURCE,
    NOSE_EYE_FEATURE_SOURCE,
    NOSE_EYE_PUPIL_FEATURE_SOURCE,
    SUPPORTED_FEATURE_SOURCES,
    reference_source,
)

MODEL_VERSION = 5

# Small L2 penalty on every coefficient except the bias. It keeps near-constant
# head-pose columns (a user holding very still) from over-fitting.
RIDGE_LAMBDA = 0.05

# Expanded columns have very different natural scales. These floors stop a
# nearly constant column from being magnified into noise by normalisation.
SCALE_FLOORS = np.array([
    0.025, 0.025,        # gx, gy
    0.025, 0.025, 0.02,  # quadratic gaze terms
    0.015, 0.015,        # yaw, pitch
    0.008, 0.008,        # gaze/head cross terms
    0.004, 0.004,        # inter-eye disagreement
])
# For the nose-eye pyramid those last two columns are the nose-apex offset.
# Landmark jitter there is ~0.01-0.02 eye units, so with a still head the
# column is pure noise; a jitter-sized floor keeps it from being amplified.
NOSE_APEX_FLOOR = 0.03
SOURCE_SCALE_FLOORS = {
    source: np.concatenate((SCALE_FLOORS[:-2], [NOSE_APEX_FLOOR, NOSE_APEX_FLOOR]))
    for source in (NOSE_EYE_FEATURE_SOURCE, NOSE_EYE_PUPIL_FEATURE_SOURCE)
}

IDENTITY_STRETCH = (0.0, 1.0, 0.0, 1.0)
# A fit that needs more than 50% expansion is itself untrustworthy; stretching
# further would only amplify noise.
MAX_EDGE_STRETCH = 1.5
MIN_STRETCH_DOTS = 5

MIN_SAMPLES = 12
MIN_GROUP_INLIERS = 8
OUTLIER_MAD_MULTIPLIER = 3.5
OUTLIER_NORMALIZED_FLOOR = 0.012


def _expand(features):
    gx, gy, dgx, dgy, yaw, pitch = features
    return np.array([
        1.0,
        gx, gy,
        gx * gx, gy * gy, gx * gy,
        yaw, pitch,
        gx * yaw, gy * pitch,
        dgx, dgy,
    ])


class CalibrationModel:
    """Fits and evaluates the gaze-to-screen regression for one feature source."""

    def __init__(self, feature_source=IRIS_FEATURE_SOURCE, reference_model=None):
        if feature_source not in SUPPORTED_FEATURE_SOURCES:
            raise ValueError(f"Unsupported calibration feature source: {feature_source}")
        self.feature_source = feature_source
        # Landmark fallback for frames where this source is missing.
        self.reference_model = reference_model
        self.coef_x = None
        self.coef_y = None
        self.rms_error = None
        # Error of each calibration dot's median prediction (screen fraction).
        # This is what the steadied pointer achieves; rms_error also counts
        # every frame's jitter.
        self.fixation_error = None
        self.feature_mean = None
        self.feature_scale = None
        self.inlier_count = None
        # Per-axis (offset_x, gain_x, offset_y, gain_y) applied after the
        # regression; identity for profiles saved before it existed.
        self.edge_stretch = IDENTITY_STRETCH

    @property
    def is_fitted(self):
        return self.coef_x is not None and self.coef_y is not None

    @property
    def accuracy(self):
        """Per-dot error when known, else the per-frame RMS error."""
        return self.fixation_error if self.fixation_error is not None else self.rms_error

    def fit(self, samples):
        """samples: list of (features, (screen_x_fraction, screen_y_fraction))."""
        if len(samples) < MIN_SAMPLES:
            raise ValueError("Not enough calibration samples to fit a model.")
        raw = np.array([_expand(feat) for feat, _ in samples], dtype=float)
        targets = np.array([target for _, target in samples], dtype=float)
        if not np.all(np.isfinite(raw)) or not np.all(np.isfinite(targets)):
            raise ValueError("Calibration data contains invalid values.")

        # Each target has the same total influence even if the frame rate
        # dipped during one point and produced fewer samples there.
        target_keys = [tuple(np.round(t, 3)) for t in targets]
        counts = {key: target_keys.count(key) for key in set(target_keys)}
        weights = np.array([1.0 / counts[key] for key in target_keys], dtype=float)

        keep = np.ones(len(samples), dtype=bool)
        self._fit_rows(raw, targets, weights, keep)

        # One robust refit removes frames captured during a saccade. Trimming
        # is per target so a hard edge point cannot disappear entirely.
        residual = np.linalg.norm(self._predict_matrix(raw) - targets, axis=1)
        for key in counts:
            idx = np.array([i for i, k in enumerate(target_keys) if k == key])
            if len(idx) < MIN_GROUP_INLIERS + 2:
                continue
            values = residual[idx]
            median = float(np.median(values))
            mad = float(np.median(np.abs(values - median)))
            cutoff = max(OUTLIER_NORMALIZED_FLOOR,
                         median + OUTLIER_MAD_MULTIPLIER * 1.4826 * mad)
            group_keep = idx[values <= cutoff]
            if len(group_keep) >= MIN_GROUP_INLIERS:
                keep[idx] = False
                keep[group_keep] = True

        self._fit_rows(raw, targets, weights, keep)
        self.edge_stretch = self._fit_edge_stretch(raw[keep], targets[keep])
        errors = self._stretch(self._predict_matrix(raw[keep])) - targets[keep]
        self.rms_error = float(np.sqrt(np.mean(np.sum(errors ** 2, axis=1))))
        self.inlier_count = int(np.sum(keep))

    def _fit_edge_stretch(self, raw, targets):
        """Undo the regression's pull toward the screen centre.

        Least squares on noisy eye features shrinks predictions toward the
        mean (errors-in-variables attenuation), so the cursor stops short of the
        edges. Per-dot medians are nearly noise-free, so a line from median
        prediction to dot position per axis measures that shrinkage. Only
        expansion is applied, capped, so a bad session cannot fling the cursor.
        """
        predicted = self._predict_matrix(raw)
        keys = [tuple(np.round(t, 3)) for t in targets]
        dots = sorted(set(keys))
        if len(dots) < MIN_STRETCH_DOTS:
            return IDENTITY_STRETCH
        medians = np.array([np.median(predicted[[k == d for k in keys]], axis=0) for d in dots])
        positions = np.array(dots, dtype=float)
        stretch = []
        for axis in (0, 1):
            m, t = medians[:, axis], positions[:, axis]
            if np.ptp(m) < 1e-6:
                stretch += [0.0, 1.0]
                continue
            gain = float(np.clip(np.polyfit(m, t, 1)[0], 1.0, MAX_EDGE_STRETCH))
            stretch += [float(np.mean(t) - gain * np.mean(m)), gain]
        return tuple(stretch)

    def _stretch(self, xy):
        ox, gx, oy, gy = self.edge_stretch
        xy = np.atleast_2d(xy).astype(float)
        return np.column_stack((ox + gx * xy[:, 0], oy + gy * xy[:, 1]))

    def _fit_rows(self, raw, targets, weights, keep):
        selected = raw[keep]
        selected_weights = weights[keep]
        weight_sum = float(np.sum(selected_weights))

        mean = np.average(selected[:, 1:], axis=0, weights=selected_weights)
        variance = np.average((selected[:, 1:] - mean) ** 2, axis=0, weights=selected_weights)
        self.feature_mean = mean
        floors = SOURCE_SCALE_FLOORS.get(self.feature_source, SCALE_FLOORS)
        self.feature_scale = np.maximum(np.sqrt(variance), floors)

        a = self._normalise_matrix(selected)
        sqrt_w = np.sqrt(selected_weights * (len(selected_weights) / weight_sum))
        aw = a * sqrt_w[:, None]
        tw = targets[keep] * sqrt_w[:, None]

        penalty = RIDGE_LAMBDA * np.eye(a.shape[1])
        penalty[0, 0] = 0.0
        ata = aw.T @ aw + penalty
        self.coef_x = np.linalg.solve(ata, aw.T @ tw[:, 0])
        self.coef_y = np.linalg.solve(ata, aw.T @ tw[:, 1])

    def _normalise_matrix(self, raw):
        a = np.array(raw, dtype=float, copy=True)
        if self.feature_mean is not None and self.feature_scale is not None:
            a[:, 1:] = (a[:, 1:] - self.feature_mean) / self.feature_scale
        return a

    def _predict_matrix(self, raw):
        a = self._normalise_matrix(raw)
        return np.column_stack((a @ self.coef_x, a @ self.coef_y))

    def predict(self, features):
        """Return the (x, y) screen fraction for one feature vector."""
        if not self.is_fitted:
            raise RuntimeError("CalibrationModel used before fit().")
        feat = self._normalise_matrix(_expand(features)[None, :])[0]
        (x, y), = self._stretch((float(feat @ self.coef_x), float(feat @ self.coef_y)))
        return float(x), float(y)

    def predict_for_screen(self, features, screen_w, screen_h):
        """Predict physical screen pixels for the current display."""
        x, y = self.predict(features)
        return x * float(screen_w), y * float(screen_h)

    def to_dict(self):
        payload = {
            "model_version": MODEL_VERSION,
            "feature_source": self.feature_source,
            "coef_x": self.coef_x.tolist(),
            "coef_y": self.coef_y.tolist(),
            "rms_error": self.rms_error,
            "fixation_error": self.fixation_error,
            "feature_mean": self.feature_mean.tolist(),
            "feature_scale": self.feature_scale.tolist(),
            "inlier_count": self.inlier_count,
            "edge_stretch": list(self.edge_stretch),
        }
        if self.reference_model is not None:
            payload["reference_model"] = self.reference_model.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data):
        """Rebuild a fitted model, or return None for an invalid/unknown payload."""
        if not isinstance(data, dict) or data.get("model_version") != MODEL_VERSION:
            return None
        source = data.get("feature_source")
        if source not in SUPPORTED_FEATURE_SOURCES:
            return None
        model = cls(feature_source=source)
        try:
            model.coef_x = np.array(data["coef_x"], dtype=float)
            model.coef_y = np.array(data["coef_y"], dtype=float)
            model.feature_mean = np.array(data["feature_mean"], dtype=float)
            model.feature_scale = np.array(data["feature_scale"], dtype=float)
            model.rms_error = float(data["rms_error"])
            fixation = data.get("fixation_error")
            model.fixation_error = float(fixation) if fixation is not None else None
            model.inlier_count = data.get("inlier_count")
            stretch = tuple(float(v) for v in data.get("edge_stretch", IDENTITY_STRETCH))
        except (KeyError, TypeError, ValueError):
            return None
        if (len(stretch) != 4 or not all(np.isfinite(stretch))
                or not (1.0 <= stretch[1] <= MAX_EDGE_STRETCH)
                or not (1.0 <= stretch[3] <= MAX_EDGE_STRETCH)):
            return None
        model.edge_stretch = stretch
        expected = len(_expand((0, 0, 0, 0, 0, 0)))
        arrays = (model.coef_x, model.coef_y, model.feature_mean, model.feature_scale)
        if (len(model.coef_x) != expected or len(model.coef_y) != expected
                or len(model.feature_mean) != len(SCALE_FLOORS)
                or len(model.feature_scale) != len(SCALE_FLOORS)
                or not all(np.all(np.isfinite(a)) for a in arrays)
                or np.any(model.feature_scale <= 0)):
            return None
        nested = data.get("reference_model")
        if nested is not None:
            reference = cls.from_dict(nested)
            if reference is None or reference.feature_source != reference_source(source):
                return None
            model.reference_model = reference
        return model
