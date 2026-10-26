"""Calibration session driven by the site over WebSocket.

The site shows the dots; this session owns the camera, collects the samples
for each dot, fits the hybrid model and, on success, saves the profile,
releases the camera and starts the tracking worker.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from app.config import Settings
from app.core.calibration.collector import (
    CALIBRATION_POINTS,
    MAX_POINT_RETRIES,
    CalibrationCollector,
    PointCollector,
)
from app.core.calibration.processor import MAX_LOW_ACCURACY_FRACTION, fit_hybrid
from app.core.calibration.profile import list_profiles, save_profile
from app.core.detection.iris_detector import DISTANCE_GUIDANCE, distance_advice
from app.core.detection.lighting import LIGHTING_GUIDANCE
from app.core.gaze.estimator import GazeTracker
from app.schemas.calibration import (
    CalibrationErrorMessage,
    CalibrationPoint,
    CalibrationProfileRead,
    CalibrationResultMessage,
    CalibrationStartMessage,
    FrameStatusMessage,
    PointResultMessage,
    ScreenSize,
    SessionReadyMessage,
)
from app.services.camera_service import CameraService
from app.services.tracking_service import TrackingService

logger = logging.getLogger("irisclick.calibration_service")

STATUS_INTERVAL_S = 1 / 15
POLL_INTERVAL_S = 0.01
REGISTERED_MIN_EAR = 0.15

Send = Callable[[BaseModel], Awaitable[None]]


class CalibrationError(Exception):
    """A user-facing problem that ends the session."""


def list_profile_summaries(settings: Settings) -> list[CalibrationProfileRead]:
    return [CalibrationProfileRead.model_validate(p.model_dump(exclude={"model"}))
            for p in list_profiles(settings.profiles_dir)]


def frame_status(reading, deep_available: bool) -> FrameStatusMessage:
    if not reading.face_found:
        return FrameStatusMessage(
            face_found=False, eyes_open=False, registered=False,
            guidance="We cannot see your face. Face the camera.",
            pupils_detected=False, deep_active=False,
        )
    eyes_open = min(reading.left_ear, reading.right_ear) >= REGISTERED_MIN_EAR
    advice = distance_advice(reading.eye_line)
    guidance = LIGHTING_GUIDANCE.get(reading.lighting_status) or (
        DISTANCE_GUIDANCE[advice] if advice else None)
    return FrameStatusMessage(
        face_found=True,
        eyes_open=eyes_open,
        registered=reading.eye_line is not None and advice is None and eyes_open,
        eye_line=reading.eye_line,
        distance_advice=advice,
        guidance=guidance,
        pupils_detected=reading.left_pupil_detected and reading.right_pupil_detected,
        deep_active=deep_available and reading.deep_features is not None,
    )


class CalibrationSession:
    def __init__(self, settings: Settings, tracking: TrackingService, cameras: CameraService,
                 send: Send):
        self._settings = settings
        self._tracking = tracking
        self._cameras = cameras
        self._send = send
        self._camera_index = 0
        self._tracker: GazeTracker | None = None
        self._status_task: asyncio.Task | None = None
        self._collector = CalibrationCollector()
        self._next_index = 0
        self._retries = 0
        self._profile_name = ""
        self._screen: ScreenSize | None = None
        self.finished = False

    async def start(self, message: CalibrationStartMessage):
        if self._tracker is not None:
            await self._send(CalibrationErrorMessage(message="Calibration already started."))
            return
        self._profile_name = message.profile_name.strip()
        self._screen = message.screen
        self._camera_index = (message.camera_index if message.camera_index is not None
                              else self._cameras.preferred_camera())
        # The worker holds the webcam; release it before opening it here.
        await asyncio.to_thread(self._tracking.stop)
        tracker = GazeTracker(
            self._settings.face_model_path,
            camera_index=self._camera_index,
            refine_pupils=self._settings.refine_pupils,
            deep_gaze=self._settings.deep_gaze_enabled,
            low_power=self._settings.low_power,
        )
        try:
            await asyncio.to_thread(tracker.start)
        except RuntimeError as exc:
            raise CalibrationError(
                f"Camera {self._camera_index + 1} could not start: {exc} "
                "Choose another camera or close apps that use it.") from exc
        self._tracker = tracker
        await asyncio.to_thread(self._cameras.set_preferred_camera, self._camera_index)
        await self._send(SessionReadyMessage(
            points=[CalibrationPoint(x=x, y=y) for x, y in CALIBRATION_POINTS],
            deep_gaze_available=tracker.deep_gaze_available,
            max_point_retries=MAX_POINT_RETRIES,
        ))
        self._status_task = asyncio.create_task(self._stream_status())

    async def _stream_status(self):
        try:
            while self._tracker is not None:
                if self._tracker.last_error:
                    await self._send(CalibrationErrorMessage(
                        message=f"Camera stopped: {self._tracker.last_error}", fatal=True))
                    return
                await self._send(frame_status(self._tracker.read(), self._tracker.deep_gaze_available))
                await asyncio.sleep(STATUS_INTERVAL_S)
        except Exception as exc:
            # The socket closed under us; the endpoint's cleanup releases the camera.
            logger.debug("Status stream ended: %s", exc)

    async def collect(self, index: int):
        if self._tracker is None:
            await self._send(CalibrationErrorMessage(message="Start the calibration first."))
            return
        if index != self._next_index:
            await self._send(CalibrationErrorMessage(
                message=f"Expected dot {self._next_index + 1}, got dot {index + 1}."))
            return

        point = PointCollector(CALIBRATION_POINTS[index], time.perf_counter())
        started = time.perf_counter()
        while not point.is_finished((time.perf_counter() - started) * 1000):
            if self._tracker.last_error:
                raise CalibrationError(f"Camera stopped: {self._tracker.last_error}")
            point.observe(self._tracker.read())
            await asyncio.sleep(POLL_INTERVAL_S)

        sample_count = len(point.cleaned_rows())
        if point.has_enough():
            self._collector.add_point(point)
            self._next_index += 1
            self._retries = 0
            await self._send(PointResultMessage(index=index, status="accepted", sample_count=sample_count))
            if self._next_index == len(CALIBRATION_POINTS):
                await self._finish()
            return

        self._retries += 1
        if self._retries >= MAX_POINT_RETRIES:
            await self._send(PointResultMessage(
                index=index, status="failed", sample_count=sample_count,
                message="Not enough clear eye images at this dot."))
            await self._fail("Not enough clear eye images at a calibration dot. "
                             "Check the lighting and try again.")
            return
        await self._send(PointResultMessage(
            index=index, status="retry", sample_count=sample_count,
            message="That dot was not clear. Rest your eyes, then we will try it again."))

    async def _finish(self):
        try:
            outcome = await asyncio.to_thread(
                fit_hybrid, self._collector.samples, self._collector.point_counts)
        except ValueError as exc:
            logger.warning("Calibration fit failed: %s", exc)
            await self._fail("Calibration did not fit. Please try again.")
            return
        if not outcome.accepted:
            logger.warning("Calibration rejected: per-dot error=%.4f (limit %.2f), source=%s",
                           outcome.accuracy, MAX_LOW_ACCURACY_FRACTION, outcome.model.feature_source)
            await self._fail("Calibration was not accurate enough. Sit at a comfortable "
                             "distance with soft front light, then try again.")
            return

        deep_available = self._tracker.deep_gaze_available
        profile = await asyncio.to_thread(
            save_profile, self._settings.profiles_dir, outcome, self._profile_name,
            self._collector.sample_count, self._screen, deep_available, self._camera_index)
        # The worker needs the camera this session still holds.
        await self._release_camera()

        worker_started = False
        message = "Calibration complete. You can close this page."
        if self._settings.auto_start_worker:
            try:
                await asyncio.to_thread(self._tracking.start, profile.id)
                worker_started = True
            except Exception as exc:
                logger.exception("Tracking worker could not start: %s", exc)
                message = "Calibration saved, but eye tracking could not start. Start it from the tray or retry."
        self.finished = True
        await self._send(CalibrationResultMessage(
            status="success",
            message=message,
            profile=CalibrationProfileRead.model_validate(profile.model_dump(exclude={"model"})),
            worker_started=worker_started,
        ))

    async def _fail(self, message: str):
        self.finished = True
        await self._release_camera()
        await self._send(CalibrationResultMessage(status="failed", message=message))

    async def _release_camera(self):
        task, self._status_task = self._status_task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        tracker, self._tracker = self._tracker, None
        if tracker is not None:
            try:
                await asyncio.to_thread(tracker.stop)
            except RuntimeError as exc:
                logger.warning("Camera release was slow: %s", exc)

    async def close(self):
        await self._release_camera()
