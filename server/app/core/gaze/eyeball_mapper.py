"""Per-eye eyeball rays: one gaze ray from each eye's centre to the screen.

``geometric_mapper`` casts a single ray from the midpoint between the eyes. Here
each eye is its own sphere: the iris offset from that eye's centre gives the
eye-in-head angle, head yaw and pitch add the head's own direction, and each
ray is cast from that eye's 3D position. The two screen hits are averaged
instead of intersecting the rays: at 40-70 cm the rays are nearly parallel, so
their crossing point is far off the screen and dominated by noise.

Features come from ``iris_detector.eyeball_features``; axes and units match
``geometric_mapper`` (camera frame, cm, webcam centred above the screen).
"""

import math

import numpy as np

from app.core.gaze.geometric_mapper import MIN_SAMPLES, RIDGE_LAMBDA, GeometricModel, _design

EYEBALL_KIND = "eyeball"
EYEBALL_VERSION = 1
# Average adult eyeball radius; makes iris offsets roughly sin(eye angle), so
# the ridge penalty works on the same scale as geometric_mapper's.
EYEBALL_RADIUS_CM = 1.2
# Head angle added to the eye angle. The eye corners sit only a few mm in front
# of the eyeball centre, so turning the head moves the iris-to-corner offset by
# well under one-to-one (~0.3-0.5 by anatomy). compare_estimators --eyeball-sweep
# on s2-s5: s2<->s3 is flat for yaw 0-0.5; s4<->s5 and s3<->s4 keep improving up
# to yaw 0.75-1.0. 0.5/0.5 is the conservative pick; negative yaw is far worse.
DEFAULT_YAW_GAIN = 0.5
DEFAULT_PITCH_GAIN = 0.5


class EyeballModel(GeometricModel):
    KIND = EYEBALL_KIND
    VERSION = EYEBALL_VERSION
    # Left eye's six design coefficients, then the right eye's.
    COEF_LENGTH = 12

    def __init__(self, feature_source: str, screen_cm: tuple[float, float] = (34.4, 19.4),
                 camera_above_cm: float = 0.8, reference_model=None,
                 yaw_gain: float = DEFAULT_YAW_GAIN, pitch_gain: float = DEFAULT_PITCH_GAIN):
        super().__init__(feature_source, screen_cm, camera_above_cm, reference_model)
        self.yaw_gain = float(yaw_gain)
        self.pitch_gain = float(pitch_gain)

    @staticmethod
    def _eyes(features):
        """((offset, origin), (offset, origin)) per eye, plus z, yaw and pitch."""
        v = [float(x) for x in features]
        eyes = (((v[0], v[1]), (v[4], v[5])), ((v[2], v[3]), (v[6], v[7])))
        return eyes, v[8], v[9], v[10]

    def fit(self, samples):
        """samples: (features, (x fraction, y fraction)); features from eyeball_features."""
        if len(samples) < MIN_SAMPLES:
            raise ValueError("Not enough calibration samples to fit a model.")
        targets = [tuple(np.round(t, 3)) for _, t in samples]
        counts = {key: targets.count(key) for key in set(targets)}
        rows = ([], [])
        angles = (([], []), ([], []))
        weights = []
        for (features, target), key in zip(samples, targets):
            if len(features) != 11 or not all(math.isfinite(float(v)) for v in features):
                continue
            eyes, z, yaw, pitch = self._eyes(features)
            if z <= 0:
                continue
            sx, sy = self._target_cm(*target)
            for side, ((ox, oy), (x, y)) in enumerate(eyes):
                rows[side].append(_design(ox / EYEBALL_RADIUS_CM, oy / EYEBALL_RADIUS_CM))
                angles[side][0].append(math.atan2(sx - x, z) - self.yaw_gain * yaw)
                angles[side][1].append(math.atan2(sy - y, z) - self.pitch_gain * pitch)
            weights.append(1.0 / counts[key])
        if len(weights) < MIN_SAMPLES:
            raise ValueError("Calibration geometry is invalid.")
        root = np.sqrt(weights)
        coef_x, coef_y = [], []
        for side in (0, 1):
            a = np.array(rows[side]) * root[:, None]
            penalty = RIDGE_LAMBDA * np.eye(a.shape[1])
            penalty[0, 0] = 0.0
            lhs = a.T @ a + penalty
            coef_x.append(np.linalg.solve(lhs, a.T @ (np.array(angles[side][0]) * root)))
            coef_y.append(np.linalg.solve(lhs, a.T @ (np.array(angles[side][1]) * root)))
        self.coef_x = np.concatenate(coef_x)
        self.coef_y = np.concatenate(coef_y)
        self.inlier_count = len(weights)
        errors = [np.hypot(*(np.array(self.predict(f)) - np.array(t))) for f, t in samples]
        self.rms_error = float(np.sqrt(np.mean(np.square(errors))))

    def predict(self, features) -> tuple[float, float]:
        """The (x, y) screen fraction for one feature vector: the mean of both eyes' hits."""
        if not self.is_fitted:
            raise RuntimeError("EyeballModel used before fit().")
        eyes, z, yaw, pitch = self._eyes(features)
        width, height = self.screen_cm
        hits = []
        for side, ((ox, oy), (x, y)) in enumerate(eyes):
            design = _design(ox / EYEBALL_RADIUS_CM, oy / EYEBALL_RADIUS_CM)
            coefs = slice(6 * side, 6 * side + 6)
            angle_x = float(design @ self.coef_x[coefs]) + self.yaw_gain * yaw
            angle_y = float(design @ self.coef_y[coefs]) + self.pitch_gain * pitch
            hits.append((x + z * math.tan(angle_x), y + z * math.tan(angle_y)))
        hx, hy = np.mean(hits, axis=0)
        tx = hx / width + 0.5
        ty = (hy - self.camera_above_cm) / height
        if self.correction is not None:
            tx, ty = self.correction.apply(tx, ty)
        return float(tx), float(ty)

    def to_dict(self) -> dict:
        return {**super().to_dict(), "yaw_gain": self.yaw_gain, "pitch_gain": self.pitch_gain}

    @classmethod
    def from_dict(cls, data: dict, reference_model=None):
        model = super().from_dict(data, reference_model)
        if model is None:
            return None
        try:
            model.yaw_gain = float(data["yaw_gain"])
            model.pitch_gain = float(data["pitch_gain"])
        except (KeyError, TypeError, ValueError):
            return None
        if not (math.isfinite(model.yaw_gain) and math.isfinite(model.pitch_gain)):
            return None
        return model
