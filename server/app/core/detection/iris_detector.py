"""Landmark math: iris position, eye-corner-relative gaze ratios, eye aspect ratio.

Landmark indices follow MediaPipe FaceLandmarker's 478-point topology
(468 face mesh points + 10 iris points).

The feature vector fed to the calibration model is richer than a single
averaged gaze ratio:

  gx, gy      average iris offset across both eyes, the primary signal
  dgx, dgy    left/right eye disagreement, which carries head-yaw information
  yaw, pitch  true head rotation from MediaPipe's facial transformation matrix

The eye-in-socket ratio only describes gaze relative to the head; without the
rotation terms the mapping drifts as soon as the head moves.
"""

import math

import numpy as np

LEFT_IRIS = [474, 475, 476, 477]
RIGHT_IRIS = [469, 470, 471, 472]

LEFT_EYE_CORNERS = (362, 263)   # inner, outer
RIGHT_EYE_CORNERS = (33, 133)   # inner, outer
NOSE_BRIDGE = 168               # between the eyes: apex anchor of the "0 V 0" pyramid
NOSE_TIP = 1
LEFT_EYE_LIDS = (386, 374)      # top, bottom
RIGHT_EYE_LIDS = (159, 145)     # top, bottom

NUM_FEATURES = 6

# The eye-line pointer is expressed in units of a third of the distance
# between the two eye centres (roughly one eye width), so its range is
# comparable to the gx/gy ratios and suits the model's scale floors.
EYE_LINE_UNIT_FRACTION = 1.0 / 3.0

# Comfortable eye-centre spacing, as a fraction of the camera frame width.
EYE_DISTANCE_MIN = 0.105
EYE_DISTANCE_MAX = 0.19

DISTANCE_GUIDANCE = {
    "closer": "Move a little closer to the screen. Your eyes look small to the camera.",
    "back": "Move back a little. Your face is too close to the camera.",
}


def _pt(landmarks, idx, w, h):
    lm = landmarks[idx]
    return np.array([lm.x * w, lm.y * h])


def eye_aspect_ratio(landmarks, top_idx, bottom_idx, left_idx, right_idx, w, h):
    top = _pt(landmarks, top_idx, w, h)
    bottom = _pt(landmarks, bottom_idx, w, h)
    left = _pt(landmarks, left_idx, w, h)
    right = _pt(landmarks, right_idx, w, h)
    horizontal = np.linalg.norm(left - right)
    if horizontal == 0:
        return 1.0
    return float(np.linalg.norm(top - bottom) / horizontal)


def iris_center(landmarks, indices, w, h):
    pts = np.array([[landmarks[i].x * w, landmarks[i].y * h] for i in indices])
    return pts.mean(axis=0)


def gaze_ratio(iris_pt, inner_pt, outer_pt):
    """Iris position as a 0-1 ratio projected onto the inner->outer corner axis."""
    span = outer_pt - inner_pt
    span_len = np.linalg.norm(span)
    if span_len == 0:
        return 0.5
    projected = np.dot(iris_pt - inner_pt, span) / span_len
    return float(np.clip(projected / span_len, 0.0, 1.0))


def head_angles(transform_matrix):
    """Yaw and pitch in radians from MediaPipe's 4x4 facial transform."""
    if transform_matrix is None:
        return 0.0, 0.0
    try:
        rot = np.array(transform_matrix, dtype=float).reshape(4, 4)[:3, :3]
        sy = math.sqrt(rot[0, 0] ** 2 + rot[1, 0] ** 2)
        if sy < 1e-6:
            return 0.0, float(math.atan2(-rot[1, 2], rot[1, 1]))
        yaw = float(math.atan2(-rot[2, 0], sy))
        pitch = float(math.atan2(rot[2, 1], rot[2, 2]))
        return yaw, pitch
    except Exception:
        return 0.0, 0.0


def compute_features(landmarks, frame_w, frame_h, transform_matrix=None, eye_centers=None):
    """Return (features, avg_ear, left_ear, right_ear).

    ``features`` is (gx, gy, dgx, dgy, yaw, pitch). ``eye_centers`` optionally
    replaces the iris-ring centres with fitted pupil centres (left, right).
    """
    if eye_centers is None:
        left_iris_pt = iris_center(landmarks, LEFT_IRIS, frame_w, frame_h)
        right_iris_pt = iris_center(landmarks, RIGHT_IRIS, frame_w, frame_h)
    else:
        left_iris_pt = np.asarray(eye_centers[0], dtype=float)
        right_iris_pt = np.asarray(eye_centers[1], dtype=float)

    l_inner = _pt(landmarks, LEFT_EYE_CORNERS[0], frame_w, frame_h)
    l_outer = _pt(landmarks, LEFT_EYE_CORNERS[1], frame_w, frame_h)
    r_inner = _pt(landmarks, RIGHT_EYE_CORNERS[0], frame_w, frame_h)
    r_outer = _pt(landmarks, RIGHT_EYE_CORNERS[1], frame_w, frame_h)
    gx_left = gaze_ratio(left_iris_pt, l_inner, l_outer)
    gx_right = gaze_ratio(right_iris_pt, r_inner, r_outer)

    l_top = _pt(landmarks, LEFT_EYE_LIDS[0], frame_w, frame_h)
    l_bottom = _pt(landmarks, LEFT_EYE_LIDS[1], frame_w, frame_h)
    r_top = _pt(landmarks, RIGHT_EYE_LIDS[0], frame_w, frame_h)
    r_bottom = _pt(landmarks, RIGHT_EYE_LIDS[1], frame_w, frame_h)
    gy_left = gaze_ratio(left_iris_pt, l_top, l_bottom)
    gy_right = gaze_ratio(right_iris_pt, r_top, r_bottom)

    gx = (gx_left + gx_right) / 2
    gy = (gy_left + gy_right) / 2
    dgx = gx_left - gx_right
    dgy = gy_left - gy_right
    yaw, pitch = head_angles(transform_matrix)

    left_ear = eye_aspect_ratio(landmarks, *LEFT_EYE_LIDS, *LEFT_EYE_CORNERS, frame_w, frame_h)
    right_ear = eye_aspect_ratio(landmarks, *RIGHT_EYE_LIDS, *RIGHT_EYE_CORNERS, frame_w, frame_h)
    return (gx, gy, dgx, dgy, yaw, pitch), (left_ear + right_ear) / 2, left_ear, right_ear


def eye_line_pointer(landmarks, frame_w, frame_h, yaw=0.0, pitch=0.0, iris_centres=None):
    """Eye-only pointer: the midpoint between both irises, on the eye line.

    The four eye corners stay fixed to the skull, so the line through the two
    eye centres moves with the head. The midpoint between the irises measured
    in that line's own frame cancels head translation, in-plane tilt and
    camera distance; only eye rotation moves it.

    Returns ``(features, info)``: features are (ex, ey, dex, dey, yaw, pitch);
    info holds normalised image points for drawing the eye view.
    """
    if iris_centres is None:
        left_iris = iris_center(landmarks, LEFT_IRIS, frame_w, frame_h)
        right_iris = iris_center(landmarks, RIGHT_IRIS, frame_w, frame_h)
    else:
        left_iris = np.asarray(iris_centres[0], dtype=float)
        right_iris = np.asarray(iris_centres[1], dtype=float)
    left_eye = (_pt(landmarks, LEFT_EYE_CORNERS[0], frame_w, frame_h)
                + _pt(landmarks, LEFT_EYE_CORNERS[1], frame_w, frame_h)) / 2
    right_eye = (_pt(landmarks, RIGHT_EYE_CORNERS[0], frame_w, frame_h)
                 + _pt(landmarks, RIGHT_EYE_CORNERS[1], frame_w, frame_h)) / 2

    axis = left_eye - right_eye
    distance = float(np.linalg.norm(axis))
    if distance <= 1e-6:
        return None, None
    along = axis / distance
    across = np.array([-along[1], along[0]])
    unit = distance * EYE_LINE_UNIT_FRACTION

    pupil_mid = (left_iris + right_iris) / 2
    eye_mid = (left_eye + right_eye) / 2
    offset = pupil_mid - eye_mid
    difference = (left_iris - left_eye) - (right_iris - right_eye)
    features = (
        float(offset @ along / unit), float(offset @ across / unit),
        float(difference @ along / unit), float(difference @ across / unit),
        float(yaw), float(pitch),
    )
    size = np.array([frame_w, frame_h], dtype=float)
    info = {
        "pointer": tuple(float(v) for v in pupil_mid / size),
        "line_centre": tuple(float(v) for v in eye_mid / size),
        "left_eye": tuple(float(v) for v in left_eye / size),
        "right_eye": tuple(float(v) for v in right_eye / size),
        "left_iris": tuple(float(v) for v in left_iris / size),
        "right_iris": tuple(float(v) for v in right_iris / size),
        # Eye-centre spacing as a fraction of frame width; drives distance advice.
        "eye_distance": distance / frame_w,
    }
    return features, info


def nose_eye_pointer(landmarks, frame_w, frame_h, yaw=0.0, pitch=0.0, iris_centres=None):
    """Nose-anchored eye pointer: the "0 V 0" pyramid.

    The nose bridge (between the eyes) is the anchor; the midpoint of both
    pupils measured from it is the pointer, so the eyes drive the cursor. The
    nose tip is the pyramid apex: its offset from the bridge in the face's own
    frame turns as the head turns, giving the mapping a head-direction signal
    so small head movements do not drag the cursor.

    Returns ``(features, points)``. Features are (ex, ey, nx, ny, yaw, pitch)
    in units of a third of the eye-centre distance; points are normalised image
    coordinates of the bridge and tip for drawing.
    """
    if iris_centres is None:
        left_iris = iris_center(landmarks, LEFT_IRIS, frame_w, frame_h)
        right_iris = iris_center(landmarks, RIGHT_IRIS, frame_w, frame_h)
    else:
        left_iris = np.asarray(iris_centres[0], dtype=float)
        right_iris = np.asarray(iris_centres[1], dtype=float)
    left_eye = (_pt(landmarks, LEFT_EYE_CORNERS[0], frame_w, frame_h)
                + _pt(landmarks, LEFT_EYE_CORNERS[1], frame_w, frame_h)) / 2
    right_eye = (_pt(landmarks, RIGHT_EYE_CORNERS[0], frame_w, frame_h)
                 + _pt(landmarks, RIGHT_EYE_CORNERS[1], frame_w, frame_h)) / 2
    bridge = _pt(landmarks, NOSE_BRIDGE, frame_w, frame_h)
    tip = _pt(landmarks, NOSE_TIP, frame_w, frame_h)

    axis = left_eye - right_eye
    distance = float(np.linalg.norm(axis))
    if distance <= 1e-6:
        return None, None
    along = axis / distance
    across = np.array([-along[1], along[0]])
    unit = distance * EYE_LINE_UNIT_FRACTION

    pupils = (left_iris + right_iris) / 2 - bridge
    apex = tip - bridge
    features = (
        float(pupils @ along / unit), float(pupils @ across / unit),
        float(apex @ along / unit), float(apex @ across / unit),
        float(yaw), float(pitch),
    )
    size = np.array([frame_w, frame_h], dtype=float)
    points = {
        "nose_bridge": tuple(float(v) for v in bridge / size),
        "nose_tip": tuple(float(v) for v in tip / size),
        # Apex in image axes, in eye-distance units. The frame is mirrored, so
        # turning the head right moves it +x and lifting the chin moves it -y,
        # matching the cursor direction the user expects for fine-tuning.
        "nose_apex": tuple(float(v) for v in apex / distance),
    }
    return features, points


def distance_advice(eye_line):
    """Return "closer", "back" or None for a reading's ``eye_line`` info."""
    if not isinstance(eye_line, dict) or "eye_distance" not in eye_line:
        return None
    spacing = eye_line["eye_distance"]
    if spacing < EYE_DISTANCE_MIN:
        return "closer"
    if spacing > EYE_DISTANCE_MAX:
        return "back"
    return None
