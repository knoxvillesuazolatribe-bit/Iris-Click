"""Appearance-based gaze features from GazeFollower's MGazeNet.

GazeFollower (Zhu et al., 2025, Proc. ACM Comput. Graph. Interact. Tech. 8(2))
ships MGazeNet, a CNN trained on webcam face images that maps a face crop, two
eye crops and their positions to a gaze point. Landmark geometry only sees
where the iris sits in the eye; the network also learns head pose, eyelid shape
and lighting, which is where a landmark mapping drifts.

Only the network is used. IrisClick keeps its own camera, MediaPipe landmarks,
calibration and filters, so the deep source is fitted and judged on exactly
the same frames as the landmark sources (the hybrid approach). ``gazefollower``
is located with ``find_spec`` for its weights only; importing it would pull in
pygame, pandas and a second OpenCV/MediaPipe install.

GazeFollower's weights are licensed CC BY-NC-SA 4.0 (non-commercial use only).
``IRISCLICK_GAZEFOLLOWER_MODEL`` points at an alternative ``.mnn`` model.
"""

import importlib.util
import logging
import math
import os
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger("irisclick.deep_gaze")

# MGazeNet's crop geometry and input sizes, reproduced from GazeFollower 1.1.0.
# The network was trained on unmirrored 640x480 RGB frames, so the 16:9 frame
# is centre-cropped to 4:3 and un-mirrored before any crop is taken.
FRAME_W, FRAME_H = 640, 480
FACE_SIZE = (224, 224)
EYE_SIZE = (112, 112)
EYE_X_PADDING = 20      # in hundredths of the inner-eye-corner distance
EYE_HEIGHT_RATIO = 0.75
EYE_ABOVE, EYE_BELOW = 0.6, 0.4
LIP_INDICES = (61, 91, 14, 178, 402, 324, 95)
EYE_CORNERS = ((33, 133), (263, 362))
INNER_CORNERS = (133, 362)


def model_path():
    override = os.environ.get("IRISCLICK_GAZEFOLLOWER_MODEL")
    if override:
        return Path(override)
    try:
        spec = importlib.util.find_spec("gazefollower")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    return Path(list(spec.submodule_search_locations)[0]) / "res" / "model_weights" / "base.mnn"


def crop_to_model_frame(frame_bgr):
    """Centre-crop an unmirrored BGR frame to 4:3 and return (rgb, crop box)."""
    h, w = frame_bgr.shape[:2]
    if w * 3 > h * 4:
        cw, ch = int(round(h * 4 / 3)), h
    else:
        cw, ch = w, int(round(w * 3 / 4))
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    crop = frame_bgr[y0:y0 + ch, x0:x0 + cw]
    rgb = cv2.cvtColor(cv2.resize(crop, (FRAME_W, FRAME_H)), cv2.COLOR_BGR2RGB)
    return rgb, (x0, y0, cw, ch)


def landmarks_to_model_frame(landmarks, width, height, crop, mirrored=True):
    """Map normalised landmarks onto the 640x480 model frame as an (n, 2) array."""
    x0, y0, cw, ch = crop
    xs = np.fromiter((lm.x for lm in landmarks), dtype=float)
    ys = np.fromiter((lm.y for lm in landmarks), dtype=float)
    if mirrored:
        xs = 1.0 - xs
    points = np.empty((len(xs), 2))
    points[:, 0] = (xs * width - x0) * (FRAME_W / cw)
    points[:, 1] = (ys * height - y0) * (FRAME_H / ch)
    return points


def _eye_box(points, outer, inner, scale):
    xa, xb = points[outer, 0], points[inner, 0]
    pad = EYE_X_PADDING * scale
    left, right = min(xa, xb) - pad, max(xa, xb) + pad
    box_h = (right - left) * EYE_HEIGHT_RATIO
    mid_y = (points[outer, 1] + points[inner, 1]) / 2.0
    return [int(left), int(mid_y - box_h * EYE_ABOVE),
            int(right), int(mid_y + box_h * EYE_BELOW)]


def crop_rects(points):
    """GazeFollower's face and eye boxes as (x, y, w, h), or None when unusable."""
    lip_y = float(np.mean(points[list(LIP_INDICES), 1]))
    if lip_y >= FRAME_H:
        return None
    min_x, min_y = max(0.0, points[:, 0].min()), max(0.0, points[:, 1].min())
    max_x = min(float(FRAME_W), points[:, 0].max())
    max_y = min(float(FRAME_H), points[:, 1].max())
    delta = ((max_x - min_x) - (max_y - min_y)) / 4
    fx0, fy0 = max(0, int(min_x + delta)), max(0, int(min_y - delta))
    fx1 = min(FRAME_W - 1, int(max_x - delta))
    fy1 = min(FRAME_H - 1, int(max_y + delta))

    scale = abs(points[INNER_CORNERS[1], 0] - points[INNER_CORNERS[0], 0]) / 100
    boxes = sorted((_eye_box(points, outer, inner, scale)
                    for outer, inner in EYE_CORNERS), key=lambda b: b[0])
    for x_0, y_0, x_1, y_1 in boxes:
        if x_0 <= 0 or y_0 <= 0 or x_1 >= FRAME_W or y_1 >= FRAME_H:
            return None
    if fx1 - fx0 < 5 or fy1 - fy0 < 5:
        return None
    face = (fx0, fy0, fx1 - fx0, fy1 - fy0)
    left, right = ((b[0], b[1], b[2] - b[0], b[3] - b[1]) for b in boxes)
    return face, left, right


def _patch(image, rect, size):
    x, y, w, h = rect
    patch = image[y:y + h, x:x + w]
    if patch.size == 0:
        return None
    return cv2.resize(patch, size).astype(np.float32) / 255.0


class DeepGazeEstimator:
    """Runs MGazeNet on one frame; used only from the tracker thread."""

    def __init__(self, path: Path):
        import MNN  # optional dependency, imported only when the model exists

        runtime = MNN.nn.create_runtime_manager(
            ({"precision": "low", "backend": 0, "numThread": 4},))
        self._module = MNN.nn.load_module_from_file(
            str(path), ["face", "left", "right", "rect"], ["output_0"],
            runtime_manager=runtime)
        self._face = MNN.expr.placeholder((1, *FACE_SIZE, 3), MNN.expr.NHWC)
        self._left = MNN.expr.placeholder((1, *EYE_SIZE, 3), MNN.expr.NHWC)
        self._right = MNN.expr.placeholder((1, *EYE_SIZE, 3), MNN.expr.NHWC)
        self._rect = MNN.expr.placeholder((1, 12))

    @classmethod
    def load(cls):
        """Return an estimator, or None when GazeFollower is unavailable."""
        path = model_path()
        if path is None or not path.is_file():
            return None
        try:
            return cls(path)
        except Exception as exc:  # missing MNN wheel, blocked DLL, bad weights
            logger.warning("GazeFollower model unavailable; using landmark sources: %s", exc)
            return None

    def estimate(self, frame_bgr, landmarks, mirrored=True):
        """Return MGazeNet's (x, y) gaze estimate, or None for an unusable frame.

        ``frame_bgr`` is the camera frame before mirroring; ``landmarks`` are
        MediaPipe's normalised landmarks for the mirrored frame.
        """
        h, w = frame_bgr.shape[:2]
        rgb, crop = crop_to_model_frame(frame_bgr)
        points = landmarks_to_model_frame(landmarks, w, h, crop, mirrored=mirrored)
        rects = crop_rects(points)
        if rects is None:
            return None
        face_rect, left_rect, right_rect = rects
        face = _patch(rgb, face_rect, FACE_SIZE)
        left = _patch(rgb, left_rect, EYE_SIZE)
        right = _patch(rgb, right_rect, EYE_SIZE)
        if face is None or left is None or right is None:
            return None
        rect = np.array([v for r in (face_rect, left_rect, right_rect)
                         for v in (r[2], r[3], r[0], r[1])], dtype=np.float32)
        rect /= np.array([FRAME_W, FRAME_H] * 6, dtype=np.float32)
        self._face.write(face)
        self._left.write(left)
        # MGazeNet expects the image-right eye mirrored to look like the left.
        self._right.write(np.ascontiguousarray(right[:, ::-1]))
        self._rect.write(rect.reshape(1, 12))
        output = self._module.onForward([self._face, self._left, self._right, self._rect])
        gaze = output[0].read().reshape(-1)[:2]
        x, y = float(gaze[0]), float(gaze[1])
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        return x, y
