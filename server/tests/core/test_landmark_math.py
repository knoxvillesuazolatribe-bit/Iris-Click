"""Landmark maths: eye openness, iris position between the eye corners, head angles, and the
binocular feature vector. Synthetic MediaPipe landmarks, no camera."""

import math
from types import SimpleNamespace

import numpy as np
import pytest

from app.core.detection import iris_detector as det

W, H = 1280, 720


def face(left_iris=(0.0, 0.0), right_iris=(0.0, 0.0), left_open=1.0, right_open=1.0):
    """478 landmarks: two eyes 30 px wide; irises offset by (dx, dy) in eye-width units.

    ``left``/``right`` here are MediaPipe's sides (the frame is mirrored before detection)."""
    points = [SimpleNamespace(x=0.5, y=0.5) for _ in range(478)]

    def put(idx, px, py):
        points[idx] = SimpleNamespace(x=px / W, y=py / H)

    def eye(corners, lids, iris, centre, offset, openness):
        cx, cy = centre
        put(corners[0], cx - 15, cy)
        put(corners[1], cx + 15, cy)
        half = 4.5 * openness
        put(lids[0], cx, cy - half)
        put(lids[1], cx, cy + half)
        ix, iy = cx + offset[0] * 30, cy + offset[1] * 9
        for k, idx in enumerate(iris):
            angle = k * math.pi / 2
            put(idx, ix + 3 * math.cos(angle), iy + 3 * math.sin(angle))

    eye(det.LEFT_EYE_CORNERS, det.LEFT_EYE_LIDS, det.LEFT_IRIS, (700, 360), left_iris, left_open)
    eye(det.RIGHT_EYE_CORNERS, det.RIGHT_EYE_LIDS, det.RIGHT_IRIS, (580, 360), right_iris, right_open)
    return points


def test_gaze_ratio_runs_from_inner_to_outer_corner():
    inner, outer = np.array([0.0, 0.0]), np.array([30.0, 0.0])
    assert det.gaze_ratio(np.array([0.0, 5.0]), inner, outer) == 0.0
    assert det.gaze_ratio(np.array([15.0, 0.0]), inner, outer) == 0.5
    assert det.gaze_ratio(np.array([45.0, 0.0]), inner, outer) == 1.0  # clipped
    assert det.gaze_ratio(np.array([3.0, 3.0]), inner, inner) == 0.5  # degenerate eye


def test_eye_aspect_ratio_falls_as_the_lid_closes():
    open_ = face()
    shut = face(left_open=0.1, right_open=0.1)
    args = (*det.LEFT_EYE_LIDS, *det.LEFT_EYE_CORNERS, W, H)
    assert det.eye_aspect_ratio(open_, *args) == pytest.approx(0.3)
    assert det.eye_aspect_ratio(shut, *args) == pytest.approx(0.03)


def test_centred_irises_give_a_centred_gaze():
    (gx, gy, dgx, dgy, yaw, pitch), ear, left_ear, right_ear = det.compute_features(face(), W, H)
    assert (gx, gy) == pytest.approx((0.5, 0.5))
    assert (dgx, dgy) == pytest.approx((0.0, 0.0))
    assert (yaw, pitch) == (0.0, 0.0)
    assert ear == pytest.approx(0.3) and left_ear == right_ear


def test_both_eyes_are_averaged_and_their_disagreement_kept():
    features, *_ = det.compute_features(face(left_iris=(0.2, 0.0), right_iris=(0.0, 0.0)), W, H)
    gx, _, dgx, _, _, _ = features
    # One eye moved 0.2 eye widths: the average moves half that, the difference keeps all of it.
    assert gx == pytest.approx(0.6) and dgx == pytest.approx(0.2)


def test_moving_the_whole_face_does_not_change_the_gaze():
    a, *_ = det.compute_features(face(left_iris=(0.1, 0.0), right_iris=(0.1, 0.0)), W, H)
    shifted = face(left_iris=(0.1, 0.0), right_iris=(0.1, 0.0))
    for p in shifted:
        p.x += 50 / W
        p.y += 30 / H
    b, *_ = det.compute_features(shifted, W, H)
    assert a[:4] == pytest.approx(b[:4])


def test_each_wink_side_is_the_users_real_eye():
    """The frame is mirrored: MediaPipe's left-eye landmarks are the user's right eye."""
    _, _, left_ear, right_ear = det.compute_features(face(left_open=0.1), W, H)
    assert right_ear < 0.05 < left_ear


def test_head_angles_from_the_facial_transform():
    assert det.head_angles(None) == (0.0, 0.0)
    assert det.head_angles(np.eye(4)) == pytest.approx((0.0, 0.0))
    yaw = math.radians(10)
    rot = np.eye(4)
    rot[:3, :3] = [[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0], [-math.sin(yaw), 0, math.cos(yaw)]]
    assert det.head_angles(rot)[0] == pytest.approx(yaw)
    pitch = math.radians(-8)
    rot = np.eye(4)
    rot[:3, :3] = [[1, 0, 0], [0, math.cos(pitch), -math.sin(pitch)], [0, math.sin(pitch), math.cos(pitch)]]
    assert det.head_angles(rot)[1] == pytest.approx(pitch)
    assert det.head_angles("not a matrix") == (0.0, 0.0)


def test_head_angles_go_into_the_features():
    yaw = math.radians(5)
    rot = np.eye(4)
    rot[:3, :3] = [[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0], [-math.sin(yaw), 0, math.cos(yaw)]]
    features, *_ = det.compute_features(face(), W, H, transform_matrix=rot)
    assert features[4] == pytest.approx(yaw)


@pytest.mark.parametrize(("spacing", "advice"), [(0.08, "closer"), (0.15, None), (0.25, "back")])
def test_distance_advice(spacing, advice):
    assert det.distance_advice({"eye_distance": spacing}) == advice
