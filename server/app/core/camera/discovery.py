"""Find the cameras a user can choose for calibration and tracking.

OpenCV exposes no device names on Windows, only indices, so each camera is
described by what it sees: resolution, brightness, whether a face is visible,
and a small JPEG snapshot the site shows so users can recognise "laptop
webcam" vs "phone" vs "USB camera".
"""

import time
from dataclasses import dataclass

import cv2
import numpy as np

from app.core.camera.capture import CAPTURE_H, CAPTURE_W
from app.core.detection.face_detector import FaceDetector

MAX_CAMERA_INDEX = 6
LIVE_FRAMES_NEEDED = 10
WARMUP_TIMEOUT_S = 3.0
# Mean grey level (0–255) below which a frame counts as blank, not just dim.
BLANK_LEVEL = 8.0
FACE_CHECK_FRAMES = 5
SNAPSHOT_WIDTH = 320
SNAPSHOT_QUALITY = 70


@dataclass(frozen=True)
class CameraProbe:
    index: int
    available: bool
    width: int = 0
    height: int = 0
    brightness: float = 0.0
    face_found: bool = False
    snapshot_jpeg: bytes | None = None


def _snapshot(frame) -> bytes | None:
    height, width = frame.shape[:2]
    scale = SNAPSHOT_WIDTH / float(width)
    small = cv2.resize(cv2.flip(frame, 1), (SNAPSHOT_WIDTH, max(1, int(height * scale))))
    ok, encoded = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, SNAPSHOT_QUALITY])
    return encoded.tobytes() if ok else None


def _is_blank(frame: np.ndarray) -> bool:
    small = cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA)
    return float(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).mean()) < BLANK_LEVEL


def read_live_frames(cap: cv2.VideoCapture) -> tuple[list[np.ndarray], np.ndarray | None]:
    """Return (live frames, last frame read) once the camera shows a real picture.

    Webcams start black while exposure settles. Virtual cameras (DroidCam, OBS)
    replay a stale cached frame, then emit a black frame when the stream
    reconnects, and only then send live video (~1 s in total). So blank frames
    reset the count and exact repeats of the previous frame are skipped.
    """
    live: list[np.ndarray] = []
    last = None
    deadline = time.monotonic() + WARMUP_TIMEOUT_S
    while len(live) < LIVE_FRAMES_NEEDED and time.monotonic() < deadline:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.01)
            continue
        if _is_blank(frame):
            live.clear()
        elif last is None or not np.array_equal(frame, last):
            live.append(frame)
        last = frame
    return live, last


def probe_camera(index: int, detector: FaceDetector) -> CameraProbe | None:
    """Describe camera ``index``; None when no device exists at that index."""
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        return None
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_H)
        frames, last = read_live_frames(cap)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        cap.release()
    if last is None:
        return CameraProbe(index=index, available=False)
    if not frames:
        # Only blank frames until the timeout: report it as the dark camera it is.
        frames = [last]

    face_found = False
    for frame in frames[-FACE_CHECK_FRAMES:]:
        rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
        landmarks, _ = detector.detect(rgb, time.perf_counter())
        face_found = face_found or landmarks is not None
    last = frames[-1]
    return CameraProbe(
        index=index, available=True, width=width, height=height,
        brightness=float(cv2.cvtColor(last, cv2.COLOR_BGR2GRAY).mean()),
        face_found=face_found, snapshot_jpeg=_snapshot(last),
    )


def probe_cameras(detector: FaceDetector, skip: set[int] | None = None) -> list[CameraProbe]:
    """Probe every index up to MAX_CAMERA_INDEX; ``skip`` lists indices in use."""
    found = []
    for index in range(MAX_CAMERA_INDEX):
        if skip and index in skip:
            found.append(CameraProbe(index=index, available=False))
            continue
        probe = probe_camera(index, detector)
        if probe is not None:
            found.append(probe)
    return found
