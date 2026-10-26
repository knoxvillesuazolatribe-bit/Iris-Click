import itertools
import time

import numpy as np

from app.core.gaze.estimator import GazeReading

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
        eye_line=None,
    )
