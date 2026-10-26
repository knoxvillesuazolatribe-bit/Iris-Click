"""Webcam ownership: open the device and always hand out the newest frame.

Reading and processing in one loop lets frames queue in the driver while the
previous one is being analysed, so the tracker would work on an image that is
already one or more frames old. ``LatestFrameGrabber`` drains the camera on its
own thread; the processing loop always takes the most recent frame and stale
ones are discarded (counted by the caller).
"""

import threading
import time

import cv2

# Request 720p; actual resolution/FPS depend on the camera and exposure.
CAPTURE_W, CAPTURE_H = 1280, 720
NORMAL_FPS = 30
LOW_POWER_FPS = 18


def open_camera(camera_index: int, low_power: bool = False) -> cv2.VideoCapture:
    """Open the webcam with IrisClick's capture settings, or raise RuntimeError."""
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError("Could not open webcam.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_H)
    cap.set(cv2.CAP_PROP_FPS, LOW_POWER_FPS if low_power else NORMAL_FPS)
    return cap


class LatestFrameGrabber:
    """Read the camera on its own thread and keep only the newest frame."""

    def __init__(self, cap: cv2.VideoCapture):
        self._cap = cap
        self._cond = threading.Condition()
        self._frame = None
        self._frame_id = 0
        self._captured_at = 0.0
        self._last_ok = time.monotonic()
        self._running = False
        self._release_on_exit = False
        self._thread = None

    def start(self):
        self._running = True
        self._last_ok = time.monotonic()
        self._thread = threading.Thread(target=self._grab, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> bool:
        """Stop reading; True once the thread has finished with the camera."""
        self._running = False
        with self._cond:
            self._cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                # A driver read is still blocked: the reader releases the
                # camera itself as soon as that read returns.
                self._release_on_exit = True
                return False
        return True

    def _grab(self):
        while self._running:
            ok, frame = self._cap.read()
            captured_at = time.perf_counter()
            with self._cond:
                if ok:
                    self._frame = frame
                    self._frame_id += 1
                    self._captured_at = captured_at
                    self._last_ok = time.monotonic()
                    self._cond.notify_all()
            if not ok:
                time.sleep(0.01)
        if self._release_on_exit:
            self._cap.release()

    def next_frame(self, after_id: int, timeout: float = 0.1):
        """Return (frame_id, frame, captured_at) newer than ``after_id``, or None."""
        with self._cond:
            if self._frame_id <= after_id:
                self._cond.wait(timeout)
            if self._frame_id <= after_id:
                return None
            return self._frame_id, self._frame, self._captured_at

    def seconds_without_frames(self) -> float:
        with self._cond:
            return time.monotonic() - self._last_ok
