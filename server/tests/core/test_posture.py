import math

from app.core.calibration.posture import (
    SUSTAIN_S,
    PostureMonitor,
    median_posture,
    posture_change,
    posture_of,
)
from app.core.gaze.estimator import GazeReading
from app.schemas.calibration import PostureReference

FRAME_S = 1 / 25
REFERENCE = PostureReference(eye_distance=0.14, yaw=-0.06, pitch=0.04)


def _reading(spacing=0.14, yaw=-0.06, pitch=0.04, face=True):
    return GazeReading(face_found=face, features=(0.5, 0.5, 0.0, 0.0, yaw, pitch),
                       eye_line={"eye_distance": spacing} if face else None)


def _feed(monitor, reading, start, seconds):
    fired, t = [], start
    while t < start + seconds:
        fired.append(monitor.update(t, reading))
        t += FRAME_S
    return fired, t


def test_posture_of_needs_a_face():
    assert posture_of(_reading(face=False)) is None
    assert posture_of(_reading()) == REFERENCE


def test_median_posture_needs_enough_frames():
    assert median_posture([REFERENCE] * 5) is None
    assert median_posture([REFERENCE] * 40) == REFERENCE


def test_small_changes_are_the_same_posture():
    # s2 -> s3: 11% closer and ~1.5 deg of head turn still transferred fine.
    current = PostureReference(eye_distance=0.155, yaw=-0.04, pitch=0.03)
    assert posture_change(REFERENCE, current) is None


def test_leaning_back_and_turning_the_head_are_changes():
    # s4 -> s5: eye spacing 0.141 -> 0.089 of the frame width.
    assert posture_change(REFERENCE, PostureReference(eye_distance=0.089, yaw=-0.06,
                                                      pitch=0.04)) == "distance"
    turned = PostureReference(eye_distance=0.14, yaw=-0.06 + math.radians(2.5),
                              pitch=0.04 - math.radians(2.5))
    assert posture_change(REFERENCE, turned) == "angle"


def test_monitor_asks_once_after_the_change_lasts():
    monitor = PostureMonitor(REFERENCE)
    fired, t = _feed(monitor, _reading(), 0.0, 8.0)
    assert not any(fired)
    fired, t = _feed(monitor, _reading(spacing=0.09), t, 12.0)
    assert fired.count(True) == 1
    assert monitor.change == "distance"
    # Sitting as before clears it.
    _feed(monitor, _reading(), t, 8.0)
    assert monitor.change is None


def test_a_brief_lean_does_not_ask():
    monitor = PostureMonitor(REFERENCE)
    _, t = _feed(monitor, _reading(), 0.0, 8.0)
    fired, t = _feed(monitor, _reading(spacing=0.09), t, SUSTAIN_S)
    fired += _feed(monitor, _reading(), t, 8.0)[0]
    assert not any(fired)


def test_new_reference_after_a_recentre_clears_the_change():
    monitor = PostureMonitor(REFERENCE)
    _, t = _feed(monitor, _reading(spacing=0.09), 0.0, 15.0)
    assert monitor.change == "distance"
    monitor.set_reference(monitor.current())
    fired, _ = _feed(monitor, _reading(spacing=0.09), t, 8.0)
    assert monitor.change is None and not any(fired)


def test_no_reference_never_asks():
    monitor = PostureMonitor(None)
    fired, _ = _feed(monitor, _reading(spacing=0.09), 0.0, 15.0)
    assert not any(fired)
