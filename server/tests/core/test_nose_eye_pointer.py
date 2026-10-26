from types import SimpleNamespace

import pytest

from app.core.detection.iris_detector import (
    LEFT_EYE_CORNERS,
    LEFT_IRIS,
    NOSE_BRIDGE,
    NOSE_TIP,
    RIGHT_EYE_CORNERS,
    RIGHT_IRIS,
    nose_eye_pointer,
)

W, H = 1280, 720


def _face(dx=0.0, dy=0.0, pupil_shift=(0.0, 0.0), tip_shift=(0.0, 0.0)):
    """Landmarks (normalised) for a frontal face, optionally translated."""
    points = [(0.5, 0.5)] * 478

    def put(index, x, y):
        points[index] = (x + dx, y + dy)

    put(RIGHT_EYE_CORNERS[0], 0.40, 0.40)
    put(RIGHT_EYE_CORNERS[1], 0.46, 0.40)
    put(LEFT_EYE_CORNERS[0], 0.54, 0.40)
    put(LEFT_EYE_CORNERS[1], 0.60, 0.40)
    px, py = pupil_shift
    for index in RIGHT_IRIS:
        put(index, 0.43 + px, 0.40 + py)
    for index in LEFT_IRIS:
        put(index, 0.57 + px, 0.40 + py)
    put(NOSE_BRIDGE, 0.50, 0.39)
    tx, ty = tip_shift
    put(NOSE_TIP, 0.50 + tx, 0.52 + ty)
    return [SimpleNamespace(x=x, y=y) for x, y in points]


def test_head_translation_does_not_move_the_pointer():
    still, _ = nose_eye_pointer(_face(), W, H)
    moved, _ = nose_eye_pointer(_face(dx=0.08, dy=-0.05), W, H)
    assert moved[:4] == pytest.approx(still[:4], abs=1e-9)


def test_eye_movement_moves_the_pointer():
    centre, _ = nose_eye_pointer(_face(), W, H)
    right, _ = nose_eye_pointer(_face(pupil_shift=(0.005, 0.0)), W, H)
    up, _ = nose_eye_pointer(_face(pupil_shift=(0.0, -0.004)), W, H)
    assert right[0] > centre[0]
    assert up[1] != pytest.approx(centre[1])
    assert right[2:4] == pytest.approx(centre[2:4])


def test_nose_apex_carries_head_direction():
    centre, points = nose_eye_pointer(_face(), W, H)
    turned, _ = nose_eye_pointer(_face(tip_shift=(0.02, 0.0)), W, H)
    assert turned[2] > centre[2]
    assert turned[:2] == pytest.approx(centre[:2])
    assert points["nose_tip"] == pytest.approx((0.50, 0.52))


def test_nose_apex_points_the_way_the_cursor_should_nudge():
    _, centre = nose_eye_pointer(_face(), W, H)
    _, right = nose_eye_pointer(_face(tip_shift=(0.01, 0.0)), W, H)
    _, lifted = nose_eye_pointer(_face(tip_shift=(0.0, -0.01)), W, H)
    assert right["nose_apex"][0] > centre["nose_apex"][0]
    assert lifted["nose_apex"][1] < centre["nose_apex"][1]
