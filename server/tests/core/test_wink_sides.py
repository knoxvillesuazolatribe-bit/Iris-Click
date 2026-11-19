"""Winks are named for the user's REAL eyes: a real left wink clicks, a real right wink right-clicks.

The tracker mirrors the camera frame (like a selfie) before MediaPipe, so the user's real left eye
is on the left of the frame and carries MediaPipe's "right eye" landmarks (33/133, lids 159/145).
"""

from types import SimpleNamespace

from app.core.detection import iris_detector as iris
from app.core.detection.blink_detector import LEFT, RIGHT, BlinkDetector

W, H = 1280, 720


def mirrored_face(real_left_closed=False, real_right_closed=False):
    """478 landmarks of a front-facing face on the MIRRORED frame."""
    points = [SimpleNamespace(x=0.5, y=0.5) for _ in range(478)]

    def eye(corners, lids, iris_ring, cx, closed):
        inner, outer = corners
        points[inner] = SimpleNamespace(x=cx + 0.03, y=0.45)
        points[outer] = SimpleNamespace(x=cx - 0.03, y=0.45)
        top, bottom = lids
        gap = 0.0005 if closed else 0.02
        points[top] = SimpleNamespace(x=cx, y=0.45 - gap / 2)
        points[bottom] = SimpleNamespace(x=cx, y=0.45 + gap / 2)
        for i in iris_ring:
            points[i] = SimpleNamespace(x=cx, y=0.45)

    # Real LEFT eye: left of the mirrored frame, MediaPipe's "right eye" landmarks.
    eye(iris.RIGHT_EYE_CORNERS, iris.RIGHT_EYE_LIDS, iris.RIGHT_IRIS, 0.42, real_left_closed)
    # Real RIGHT eye: right of the mirrored frame, MediaPipe's "left eye" landmarks.
    eye(iris.LEFT_EYE_CORNERS, iris.LEFT_EYE_LIDS, iris.LEFT_IRIS, 0.58, real_right_closed)
    return points


def ears(**closed):
    _features, _avg, left_ear, right_ear = iris.compute_features(mirrored_face(**closed), W, H)
    return left_ear, right_ear


def test_a_real_left_wink_is_a_left_wink():
    left_ear, right_ear = ears(real_left_closed=True)
    assert left_ear < 0.05 < right_ear
    assert BlinkDetector().classify(left_ear, right_ear) == LEFT  # left wink = click


def test_a_real_right_wink_is_a_right_wink():
    left_ear, right_ear = ears(real_right_closed=True)
    assert right_ear < 0.05 < left_ear
    assert BlinkDetector().classify(left_ear, right_ear) == RIGHT  # right wink = right-click


def test_open_eyes_are_not_a_wink():
    assert BlinkDetector().classify(*ears()) is None
