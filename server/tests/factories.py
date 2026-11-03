import itertools
import time

import math

import numpy as np

from app.core.gaze.estimator import GazeReading
from app.core.gaze.eyeball_mapper import DEFAULT_PITCH_GAIN, DEFAULT_YAW_GAIN, EYEBALL_RADIUS_CM

SCREEN_CM = (34.4, 19.4)
CAMERA_ABOVE_CM = 0.8
# Radians of eye rotation per unit of pupil-midpoint offset (synthetic).
EYE_GAIN = 1.5


def geometry_features(target, eye=(0.0, 8.0, 55.0), pitch=-0.01):
    """Geometry features of an eye at ``eye`` (cm) looking at ``target`` (fractions)."""
    x, y, z = eye
    sx = (target[0] - 0.5) * SCREEN_CM[0]
    sy = target[1] * SCREEN_CM[1] + CAMERA_ABOVE_CM
    gx = math.atan2(sx - x, z) / EYE_GAIN
    gy = (math.atan2(sy - y, z) - pitch) / EYE_GAIN
    return gx, gy, x, y, z, pitch


def eyeball_features(target, eye=(0.0, 8.0, 55.0), yaw=0.0, pitch=-0.01):
    """Eyeball features of eyes centred on ``eye`` (cm) looking at ``target`` (fractions)."""
    x, y, z = eye
    sx = (target[0] - 0.5) * SCREEN_CM[0]
    sy = target[1] * SCREEN_CM[1] + CAMERA_ABOVE_CM
    offsets, origins = [], []
    for ex in (x + 3.15, x - 3.15):
        ax = math.atan2(sx - ex, z) - DEFAULT_YAW_GAIN * yaw
        ay = math.atan2(sy - y, z) - DEFAULT_PITCH_GAIN * pitch
        offsets += [EYEBALL_RADIUS_CM * ax / EYE_GAIN, EYEBALL_RADIUS_CM * ay / EYE_GAIN]
        origins += [ex, y]
    return (*offsets, *origins, z, yaw, pitch)


_frame_ids = itertools.count(1)


def synthetic_reading(target, rng, noise=0.002, deep=True, pupils=True, nose=True,
                      left_ear=0.3, right_ear=0.3):
    """A face frame whose features are a smooth function of the gaze target."""
    tx, ty = target

    def jitter(values):
        return tuple(float(v) for v in np.asarray(values) + rng.normal(0, noise, len(values)))

    iris = jitter((0.35 + 0.3 * tx, 0.4 + 0.2 * ty, 0.01 * tx, 0.0, 0.02, -0.01))
    midpoint = jitter((-0.4 + 0.8 * tx, -0.3 + 0.6 * ty, 0.02 * tx, 0.0, 0.02, -0.01))
    nose_eye = jitter((-0.4 + 0.8 * tx, 0.2 + 0.6 * ty, 0.05 * tx, 2.1, 0.02, -0.01))
    return GazeReading(
        face_found=True,
        features=iris,
        left_ear=left_ear,
        right_ear=right_ear,
        captured_at=time.perf_counter(),
        frame_id=next(_frame_ids),
        pupil_features=jitter(iris) if pupils else None,
        midpoint_features=midpoint,
        pupil_midpoint_features=jitter(midpoint) if pupils else None,
        deep_features=jitter((tx, ty, 0.0, 0.0, 0.02, -0.01)) if deep else None,
        nose_features=nose_eye if nose else None,
        pupil_nose_features=jitter(nose_eye) if nose and pupils else None,
        geometry_features=jitter(geometry_features(target)),
        pupil_geometry_features=jitter(geometry_features(target)) if pupils else None,
        eyeball_features=jitter(eyeball_features(target)),
        pupil_eyeball_features=jitter(eyeball_features(target)) if pupils else None,
        eye_line=None,
    )
