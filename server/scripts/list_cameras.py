r"""Lists the cameras OpenCV can open, to choose CAMERA_INDEX. Run from server\:

    .venv\Scripts\python scripts\list_cameras.py

Read-only: grabs a few frames per index and releases it. For each camera it
reports whether the picture is live (a disconnected DroidCam shows a frozen
placeholder) and whether a face is found. No image is saved or shown. A camera
already in use (e.g. by a calibration or video call) shows as "no image".
"""

import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.core.camera.capture import CAPTURE_H, CAPTURE_W  # noqa: E402
from app.core.detection.face_detector import FaceDetector  # noqa: E402

MAX_INDEX = 6
FRAMES = 15
# Sensor noise alone changes a live picture by more than this mean grey level.
LIVE_DIFF = 0.5
# Space the reads out: compressed video barely changes between adjacent frames.
FRAME_GAP_S = 0.1
ROTATIONS = {"90": cv2.ROTATE_90_CLOCKWISE, "180": cv2.ROTATE_180, "270": cv2.ROTATE_90_COUNTERCLOCKWISE}


def probe(index: int, detector: FaceDetector, backend: int = cv2.CAP_ANY) -> str | None:
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_H)
    frames = []
    for _ in range(FRAMES):
        time.sleep(FRAME_GAP_S)
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if len(frames) < 2:
        return f"index {index}: opens but returns no image (busy or disconnected)"
    grey = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32) for f in frames[::3]]
    change = float(np.mean([np.abs(a - b).mean() for a, b in zip(grey, grey[1:])]))
    faces = 0
    for frame in frames[-5:]:
        landmarks, _ = detector.detect(cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB),
                                       time.perf_counter())
        faces += landmarks is not None
    rotated = ""
    if faces == 0:
        for name, code in ROTATIONS.items():
            hits = sum(detector.detect(cv2.cvtColor(cv2.flip(cv2.rotate(f, code), 1), cv2.COLOR_BGR2RGB),
                                       time.perf_counter())[0] is not None for f in frames[-5:])
            if hits:
                rotated = f"; face found when rotated {name} ({hits}/5): set CAMERA_ROTATION={name}"
                break
    live = "live" if change > LIVE_DIFF else "FROZEN picture (phone app not connected?)"
    return (f"index {index}: {width}x{height}, {live}, brightness {grey[-1].mean():.0f}, "
            f"face found in {faces}/5 frames{rotated}")


def main() -> int:
    detector = FaceDetector(get_settings().face_model_path)
    try:
        # Some virtual cameras (older DroidCam, OBS) exist only for DirectShow.
        for label, backend in (("msmf", cv2.CAP_MSMF), ("dshow", cv2.CAP_DSHOW)):
            print(f"[{label}] CAMERA_BACKEND={label}")
            for index in range(MAX_INDEX):
                line = probe(index, detector, backend)
                if line:
                    print(f"  {line}")
    finally:
        detector.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
