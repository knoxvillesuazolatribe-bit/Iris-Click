"""MediaPipe FaceLandmarker (478 points: 468 face mesh + 10 iris) in video mode."""

import time
from pathlib import Path

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    RunningMode,
)


class MonotonicClock:
    """Strictly increasing millisecond timestamps, required by detect_for_video."""

    def __init__(self):
        self._start = time.perf_counter()
        self._last_ms = -1

    def next_ms(self, captured_at: float | None = None) -> int:
        stamp = time.perf_counter() if captured_at is None else captured_at
        ms = int((stamp - self._start) * 1000)
        if ms <= self._last_ms:
            ms = self._last_ms + 1
        self._last_ms = ms
        return ms


class FaceDetector:
    """Wraps the landmarker; returns (landmarks, transform_matrix) or (None, None)."""

    def __init__(self, model_path: Path):
        if not Path(model_path).is_file():
            raise RuntimeError(f"Face landmark model not found: {model_path}")
        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = FaceLandmarker.create_from_options(options)
        self._clock = MonotonicClock()

    def detect(self, rgb_frame, captured_at: float):
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self._landmarker.detect_for_video(image, self._clock.next_ms(captured_at))
        if not result.face_landmarks:
            return None, None
        matrices = getattr(result, "facial_transformation_matrixes", None)
        return result.face_landmarks[0], (matrices[0] if matrices else None)

    def close(self):
        self._landmarker.close()
