"""Webcam ownership: open the device and always hand out the newest frame.

Reading and processing in one loop lets frames queue in the driver while the
previous one is being analysed, so the tracker would work on an image that is
already one or more frames old. ``LatestFrameGrabber`` drains the camera on its
own thread; the processing loop always takes the most recent frame and stale
ones are discarded (counted by the caller).
"""

import threading
import time
from collections import deque

import cv2

# Requested size; the driver may negotiate another size and FPS (see describe_camera).
RESOLUTIONS = {"720p": (1280, 720), "1080p": (1920, 1080), "1440p": (2560, 1440)}
# Camera discovery snapshots always use 720p.
CAPTURE_W, CAPTURE_H = RESOLUTIONS["720p"]
NORMAL_FPS = 30
LOW_POWER_FPS = 18
# "auto" lets OpenCV choose, which is Media Foundation (MSMF) on Windows.
BACKENDS = {"auto": cv2.CAP_ANY, "msmf": cv2.CAP_MSMF, "dshow": cv2.CAP_DSHOW}
# Every delivered frame's (read return, driver timestamp); ~11 min at 30 fps.
DELIVERY_LOG_FRAMES = 20_000


def open_camera(camera_index: int, low_power: bool = False, backend: str = "auto",
                fourcc: str = "", resolution: str = "720p") -> cv2.VideoCapture:
    """Open the webcam with IrisClick's capture settings, or raise RuntimeError.

    ``fourcc`` (e.g. "MJPG") asks for a pixel format; USB 2.0 webcams can only
    sustain 720p30 compressed, uncompressed YUY2 720p tops out near 10 fps.
    """
    if backend not in BACKENDS:
        raise RuntimeError(f"Unknown camera backend {backend!r}.")
    if resolution not in RESOLUTIONS:
        raise RuntimeError(f"Unknown camera resolution {resolution!r}.")
    cap = cv2.VideoCapture(camera_index, BACKENDS[backend])
    if not cap.isOpened():
        cap.release()
        raise RuntimeError("Could not open webcam.")
    width, height = RESOLUTIONS[resolution]
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, LOW_POWER_FPS if low_power else NORMAL_FPS)
    # Measured on the built-in UVC webcam: DirectShow keeps YUY2 unless the
    # format is set after size and fps (other orders are silently ignored).
    if fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    return cap


def describe_camera(cap: cv2.VideoCapture) -> dict:
    """What the driver actually negotiated (requests can be silently ignored)."""
    code = int(cap.get(cv2.CAP_PROP_FOURCC))
    fourcc = "".join(chr((code >> 8 * i) & 0xFF) for i in range(4)) if code > 0 else ""
    # MSMF reports a media-subtype code here, not printable FOURCC characters.
    if fourcc and not fourcc.strip("\x00 ").isprintable():
        fourcc = f"code {code}"
    try:
        backend = cap.getBackendName()
    except cv2.error:
        backend = "unknown"
    return {
        "backend": backend,
        "fourcc": fourcc.strip("\x00 ") or "unknown",
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": round(float(cap.get(cv2.CAP_PROP_FPS)), 2),
    }


class LatestFrameGrabber:
    """Read the camera on its own thread and keep only the newest frame."""

    def __init__(self, cap: cv2.VideoCapture):
        self._cap = cap
        self._cond = threading.Condition()
        self._frame = None
        self._frame_id = 0
        self._captured_at = 0.0
        self._camera_ms = None
        self._last_ok = time.monotonic()
        self._running = False
        self._release_on_exit = False
        self._thread = None
        self.deliveries: deque[tuple[float, float | None]] = deque(maxlen=DELIVERY_LOG_FRAMES)

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
            # Driver sample time (ms from stream start), not the perf_counter
            # clock: only differences between frames are meaningful.
            camera_ms = self._cap.get(cv2.CAP_PROP_POS_MSEC) if ok else 0.0
            camera_ms = camera_ms if camera_ms > 0 else None
            with self._cond:
                if ok:
                    self._frame = frame
                    self._frame_id += 1
                    self._captured_at = captured_at
                    self._camera_ms = camera_ms
                    self._last_ok = time.monotonic()
                    self.deliveries.append((captured_at, camera_ms))
                    self._cond.notify_all()
            if not ok:
                time.sleep(0.01)
        if self._release_on_exit:
            self._cap.release()

    def next_frame(self, after_id: int, timeout: float = 0.1):
        """Return (frame_id, frame, captured_at, camera_ms) newer than ``after_id``, or None."""
        with self._cond:
            if self._frame_id <= after_id:
                self._cond.wait(timeout)
            if self._frame_id <= after_id:
                return None
            return self._frame_id, self._frame, self._captured_at, self._camera_ms

    def delivery_log(self) -> list[tuple[float, float | None]]:
        with self._cond:
            return list(self.deliveries)

    def seconds_without_frames(self) -> float:
        with self._cond:
            return time.monotonic() - self._last_ok
