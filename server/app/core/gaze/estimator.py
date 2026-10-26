"""Background camera + face/iris/pupil/deep-gaze estimation loop.

``GazeTracker`` owns the webcam and models and runs detection on its own
thread, publishing the latest ``GazeReading`` under a lock. Consumers (the
calibration session, the tracking worker) poll ``read()`` at their own pace,
which keeps every UI and OS-input call on the consumer's thread.
"""

import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import cv2

from app.core.camera.capture import LatestFrameGrabber, open_camera
from app.core.detection.face_detector import FaceDetector
from app.core.detection.iris_detector import (
    compute_features,
    eye_line_pointer,
    nose_eye_pointer,
)
from app.core.detection.lighting import face_lighting_status
from app.core.detection.pupil_detector import (
    LEFT_EYE_CONTOUR,
    RIGHT_EYE_CONTOUR,
    PupilLocalizer,
)
from app.core.gaze.deep_gaze import DeepGazeEstimator

PUPIL_MIN_CONFIDENCE = 0.40
CLOSED_EAR = 0.10
LOW_POWER_FRAME_INTERVAL = 1.0 / 18.0
START_TIMEOUT_S = 15.0
FIRST_FRAME_TIMEOUT_S = 4.0
NO_FRAME_ERROR_S = 3.0

LEFT_IRIS_RING = (474, 475, 476, 477)
RIGHT_IRIS_RING = (469, 470, 471, 472)

logger = logging.getLogger("irisclick.tracker")


@dataclass
class GazeReading:
    face_found: bool
    features: tuple = (0.5, 0.5, 0.0, 0.0, 0.0, 0.0)
    ear: float = 1.0
    left_ear: float = 1.0
    right_ear: float = 1.0
    captured_at: float = 0.0  # perf_counter seconds after camera read
    frame_id: int = 0
    pupil_features: tuple | None = None
    midpoint_features: tuple | None = None
    pupil_midpoint_features: tuple | None = None
    deep_features: tuple | None = None
    nose_features: tuple | None = None
    pupil_nose_features: tuple | None = None
    eye_line: dict | None = None
    left_pupil_detected: bool = False
    right_pupil_detected: bool = False
    lighting_status: str = "unknown"


class GazeTracker:
    """Owns the webcam and the models; runs estimation on a background thread."""

    def __init__(self, model_path: Path, camera_index: int = 0, refine_pupils: bool = True,
                 deep_gaze: bool = True, low_power: bool = False):
        self._model_path = Path(model_path)
        self._camera_index = camera_index
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        self._reading = GazeReading(face_found=False)
        self._running = False
        self._thread: threading.Thread | None = None
        self._cap = None
        self._error: str | None = None
        self._ready_event = threading.Event()
        self.refine_pupils = refine_pupils
        self.deep_gaze = deep_gaze
        self.deep_gaze_available = False
        self.low_power = low_power
        self._pupil_localizer = PupilLocalizer()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._error

    def read(self) -> GazeReading:
        with self._lock:
            return self._reading

    def start(self):
        with self._lifecycle_lock:
            if self._running:
                return
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("The previous camera worker is still stopping. Try again.")
            with self._lock:
                self._error = None
                self._reading = GazeReading(face_found=False)
            self._ready_event.clear()
            self._cap = open_camera(self._camera_index, self.low_power)
            self._running = True
            self._thread = threading.Thread(target=self._run, name="gaze-tracker", daemon=True)
            self._thread.start()
            if not self._ready_event.wait(timeout=START_TIMEOUT_S):
                self.stop()
                raise RuntimeError("Eye-tracking model initialisation timed out.")
            if self.last_error:
                error = self.last_error
                self.stop()
                raise RuntimeError(error)
            # Opening a handle is not proof that frames arrive: some drivers
            # open while another application still owns the stream.
            deadline = time.monotonic() + FIRST_FRAME_TIMEOUT_S
            while time.monotonic() < deadline:
                if self.read().frame_id > 0:
                    return
                if self.last_error or not self._running:
                    break
                time.sleep(0.02)
            error = self.last_error or "The webcam opened but did not return a usable frame."
            self.stop()
            raise RuntimeError(error)

    def stop(self):
        with self._lifecycle_lock:
            self._running = False
            if self._thread is not None:
                self._thread.join(timeout=3.0)
                if self._thread.is_alive():
                    raise RuntimeError("The camera is taking longer to stop. Wait, then retry.")
            if self._cap is not None:
                self._cap.release()
                self._cap = None
            self._thread = None

    def _run(self):
        detector = None
        grabber = None
        deep_estimator = None
        stats = Counter()
        try:
            detector = FaceDetector(self._model_path)
            if self.deep_gaze:
                deep_estimator = DeepGazeEstimator.load()
            self.deep_gaze_available = deep_estimator is not None
            logger.info("Tracker ready (GazeFollower deep source: %s)",
                        "on" if self.deep_gaze_available else "off")
            self._ready_event.set()

            grabber = LatestFrameGrabber(self._cap)
            grabber.start()
            frame_id = 0
            grab_id = 0
            while self._running:
                item = grabber.next_frame(grab_id)
                if item is None:
                    if grabber.seconds_without_frames() >= NO_FRAME_ERROR_S:
                        raise RuntimeError("The webcam stopped returning frames. Check its connection.")
                    continue
                loop_started = time.perf_counter()
                newest_id, camera_frame, captured_at = item
                stats["dropped"] += max(0, newest_id - grab_id - 1)
                grab_id = newest_id
                frame_id += 1
                reading = self._process(camera_frame, captured_at, frame_id,
                                        detector, deep_estimator, stats)
                stats["frames"] += 1
                stats["faces"] += int(reading.face_found)
                with self._lock:
                    self._reading = reading
                if self.low_power:
                    remaining = LOW_POWER_FRAME_INTERVAL - (time.perf_counter() - loop_started)
                    if remaining > 0:
                        time.sleep(remaining)
        except Exception as exc:
            logger.exception("Camera/tracking worker stopped: %s", exc)
            with self._lock:
                self._error = str(exc)
                self._reading = GazeReading(face_found=False)
        finally:
            if stats["frames"]:
                logger.info("Tracker session: %s", dict(stats))
            self._running = False
            if grabber is not None:
                grabber.stop()
            self._ready_event.set()
            if detector is not None:
                detector.close()

    def _process(self, camera_frame, captured_at, frame_id, detector, deep_estimator, stats):
        # Mirror so the user's left is image-left, like looking in a mirror.
        frame = cv2.flip(camera_frame, 1)
        h, w = frame.shape[:2]
        landmarks, transform = detector.detect(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), captured_at)
        if landmarks is None:
            return GazeReading(face_found=False, captured_at=captured_at, frame_id=frame_id)

        features, ear, l_ear, r_ear = compute_features(landmarks, w, h, transform_matrix=transform)
        mid_features, eye_line = eye_line_pointer(landmarks, w, h, yaw=features[4], pitch=features[5])
        nose_features, nose_points = nose_eye_pointer(
            landmarks, w, h, yaw=features[4], pitch=features[5])
        if eye_line is not None and nose_points is not None:
            eye_line = {**eye_line, **nose_points}
        pupil_features = pupil_mid_features = pupil_nose_features = None
        left_detected = right_detected = False
        if self.refine_pupils:
            try:
                left = self._pupil_localizer.estimate(
                    frame, landmarks, LEFT_IRIS_RING, LEFT_EYE_CONTOUR,
                    width=w, height=h, eye_open=l_ear >= CLOSED_EAR)
                right = self._pupil_localizer.estimate(
                    frame, landmarks, RIGHT_IRIS_RING, RIGHT_EYE_CONTOUR,
                    width=w, height=h, eye_open=r_ear >= CLOSED_EAR)
                left_detected = left.detected and left.confidence >= PUPIL_MIN_CONFIDENCE
                right_detected = right.detected and right.confidence >= PUPIL_MIN_CONFIDENCE
                # A pupil source only consumes actually fitted pupils; an
                # iris-prior fallback would mix two coordinate systems.
                if left_detected and right_detected:
                    centres = (left.center, right.center)
                    pupil_features, _, _, _ = compute_features(
                        landmarks, w, h, transform_matrix=transform, eye_centers=centres)
                    pupil_mid_features, _ = eye_line_pointer(
                        landmarks, w, h, yaw=features[4], pitch=features[5], iris_centres=centres)
                    pupil_nose_features, _ = nose_eye_pointer(
                        landmarks, w, h, yaw=features[4], pitch=features[5], iris_centres=centres)
            except Exception as exc:
                stats["pupil_errors"] += 1
                if stats["pupil_errors"] == 1:
                    logger.exception("Pupil refinement failed; using landmarks: %s", exc)

        deep_features = None
        # A closed eye gives the network nothing to read.
        if deep_estimator is not None and min(l_ear, r_ear) >= CLOSED_EAR:
            try:
                gaze = deep_estimator.estimate(camera_frame, landmarks)
                if gaze is not None:
                    deep_features = (gaze[0], gaze[1], 0.0, 0.0, features[4], features[5])
                    stats["deep_frames"] += 1
            except Exception as exc:
                stats["deep_errors"] += 1
                if stats["deep_errors"] == 1:
                    logger.exception("GazeFollower estimate failed; using landmarks: %s", exc)

        return GazeReading(
            face_found=True, features=features, ear=ear, left_ear=l_ear, right_ear=r_ear,
            captured_at=captured_at, frame_id=frame_id,
            pupil_features=pupil_features, midpoint_features=mid_features,
            pupil_midpoint_features=pupil_mid_features, deep_features=deep_features,
            nose_features=nose_features, pupil_nose_features=pupil_nose_features,
            eye_line=eye_line, left_pupil_detected=left_detected,
            right_pupil_detected=right_detected,
            lighting_status=face_lighting_status(frame, landmarks),
        )
