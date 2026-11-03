"""Posture-robust mapping: a gaze ray from the 3D eye position to the screen.

The regression in ``screen_mapper`` learns everything from 13 dots looked at
from one posture, so leaning or shifting later moves the cursor. Here the
calibration only learns how the eyes rotate in the head (two angles from the
pupil-midpoint offset); where the eyes are and how the head is pitched come
from geometry every frame:

    screen point = eye position + distance * tan(eye angle + head pitch)

Camera frame: x right and y down as seen by the user, z toward the user,
origin at the webcam, which sits centred just above the screen's top edge.
Lengths are cm. Yaw is not added: on recordings s1-s3 it made cross-sitting
error worse with either sign (the eye offset already carries it).

Fitted on s1-s3 and scored on the other sittings: 129 px median / 152 px
worst, versus 160 / 186 for the eye-only regression.
"""

import math

import numpy as np

from app.core.gaze.screen_mapper import IDENTITY_STRETCH, ScreenCorrection

GEOMETRY_KIND = "geometric"
GEOMETRY_VERSION = 1
# Head pitch adds to the eyes' vertical angle one-to-one (physics; the sweep
# on s1-s3 found 1.0-1.25 equally good).
PITCH_GAIN = 1.0
MIN_SAMPLES = 12
# Small L2 penalty on the non-bias angle terms, in radians per feature unit.
RIDGE_LAMBDA = 1e-4


def _design(gx: float, gy: float) -> np.ndarray:
    return np.array([1.0, gx, gy, gx * gx, gy * gy, gx * gy])


class GeometricModel:
    """Same interface as ``CalibrationModel`` (predict, fit, to_dict, ...)."""

    KIND = GEOMETRY_KIND
    VERSION = GEOMETRY_VERSION
    COEF_LENGTH = 6

    def __init__(self, feature_source: str, screen_cm: tuple[float, float] = (34.4, 19.4),
                 camera_above_cm: float = 0.8, reference_model=None):
        self.feature_source = feature_source
        self.screen_cm = (float(screen_cm[0]), float(screen_cm[1]))
        self.camera_above_cm = float(camera_above_cm)
        self.reference_model = reference_model
        self.coef_x = None
        self.coef_y = None
        self.rms_error = None
        self.fixation_error = None
        self.validation_error = None
        self.held_out_dot_errors: dict | None = None
        self.inlier_count = None
        # Kept for the shared interface: geometry already reaches the edges.
        self.edge_stretch = IDENTITY_STRETCH
        self.correction: ScreenCorrection | None = None

    @property
    def is_fitted(self) -> bool:
        return self.coef_x is not None and self.coef_y is not None

    @property
    def accuracy(self) -> float:
        return self.fixation_error if self.fixation_error is not None else self.rms_error

    def _target_cm(self, tx: float, ty: float) -> tuple[float, float]:
        width, height = self.screen_cm
        return (tx - 0.5) * width, ty * height + self.camera_above_cm

    def fit(self, samples):
        """samples: (features, (x fraction, y fraction)); features from eye_geometry_features."""
        if len(samples) < MIN_SAMPLES:
            raise ValueError("Not enough calibration samples to fit a model.")
        rows, angles_x, angles_y = [], [], []
        targets = [tuple(np.round(t, 3)) for _, t in samples]
        counts = {key: targets.count(key) for key in set(targets)}
        weights = []
        for (features, target), key in zip(samples, targets):
            gx, gy, x, y, z, pitch = (float(v) for v in features)
            if z <= 0 or not all(math.isfinite(v) for v in (gx, gy, x, y, z, pitch)):
                continue
            sx, sy = self._target_cm(*target)
            rows.append(_design(gx, gy))
            angles_x.append(math.atan2(sx - x, z))
            angles_y.append(math.atan2(sy - y, z) - PITCH_GAIN * pitch)
            weights.append(1.0 / counts[key])
        if len(rows) < MIN_SAMPLES:
            raise ValueError("Calibration geometry is invalid.")
        a = np.array(rows) * np.sqrt(weights)[:, None]
        penalty = RIDGE_LAMBDA * np.eye(a.shape[1])
        penalty[0, 0] = 0.0
        lhs = a.T @ a + penalty
        self.coef_x = np.linalg.solve(lhs, a.T @ (np.array(angles_x) * np.sqrt(weights)))
        self.coef_y = np.linalg.solve(lhs, a.T @ (np.array(angles_y) * np.sqrt(weights)))
        self.inlier_count = len(rows)
        errors = [np.hypot(*(np.array(self.predict(f)) - np.array(t))) for f, t in samples]
        self.rms_error = float(np.sqrt(np.mean(np.square(errors))))

    def predict(self, features) -> tuple[float, float]:
        """The (x, y) screen fraction for one feature vector."""
        if not self.is_fitted:
            raise RuntimeError("GeometricModel used before fit().")
        gx, gy, x, y, z, pitch = (float(v) for v in features)
        design = _design(gx, gy)
        angle_x = float(design @ self.coef_x)
        angle_y = float(design @ self.coef_y) + PITCH_GAIN * pitch
        width, height = self.screen_cm
        tx = (x + z * math.tan(angle_x)) / width + 0.5
        ty = (y + z * math.tan(angle_y) - self.camera_above_cm) / height
        if self.correction is not None:
            tx, ty = self.correction.apply(tx, ty)
        return tx, ty

    def predict_for_screen(self, features, screen_w, screen_h):
        x, y = self.predict(features)
        return x * float(screen_w), y * float(screen_h)

    def set_correction(self, correction: ScreenCorrection | None):
        self.correction = correction
        if self.reference_model is not None:
            self.reference_model.set_correction(correction)

    def to_dict(self) -> dict:
        payload = {
            "kind": self.KIND,
            "geometry_version": self.VERSION,
            "feature_source": self.feature_source,
            "screen_cm": list(self.screen_cm),
            "camera_above_cm": self.camera_above_cm,
            "coef_x": self.coef_x.tolist(),
            "coef_y": self.coef_y.tolist(),
            "rms_error": self.rms_error,
            "fixation_error": self.fixation_error,
            "validation_error": self.validation_error,
            "held_out_dot_errors": ([[float(x), float(y), float(e)]
                                     for (x, y), e in self.held_out_dot_errors.items()]
                                    if self.held_out_dot_errors else None),
            "inlier_count": self.inlier_count,
        }
        if self.reference_model is not None:
            payload["reference_model"] = self.reference_model.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict, reference_model=None):
        """Rebuild a fitted model, or None for an invalid payload."""
        if data.get("geometry_version") != cls.VERSION:
            return None
        try:
            width, height = (float(v) for v in data["screen_cm"])
            model = cls(data["feature_source"], (width, height), float(data["camera_above_cm"]),
                        reference_model)
            model.coef_x = np.array(data["coef_x"], dtype=float)
            model.coef_y = np.array(data["coef_y"], dtype=float)
            model.rms_error = float(data["rms_error"])
            for name in ("fixation_error", "validation_error"):
                value = data.get(name)
                setattr(model, name, float(value) if value is not None else None)
            dots = data.get("held_out_dot_errors")
            model.held_out_dot_errors = ({(float(x), float(y)): float(e) for x, y, e in dots}
                                         if dots else None)
            model.inlier_count = data.get("inlier_count")
        except (KeyError, TypeError, ValueError):
            return None
        expected = cls.COEF_LENGTH
        if (len(model.coef_x) != expected or len(model.coef_y) != expected
                or not np.all(np.isfinite(model.coef_x)) or not np.all(np.isfinite(model.coef_y))
                or width <= 0 or height <= 0):
            return None
        return model
