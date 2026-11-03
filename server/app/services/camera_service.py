"""Camera choice: scan connected cameras and remember the one the user picked."""

import logging
import threading
from functools import lru_cache

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.core.calibration.profile import load_profile
from app.core.camera.discovery import probe_cameras
from app.core.detection.face_detector import FaceDetector
from app.schemas.camera import CameraRead, DeviceSettings
from app.services.tracking_service import TrackingService, get_tracking_service

logger = logging.getLogger("irisclick.camera_service")


def read_device_settings(settings: Settings) -> DeviceSettings:
    try:
        return DeviceSettings.model_validate_json(settings.device_settings_path.read_text("utf-8"))
    except FileNotFoundError:
        return DeviceSettings(camera_index=settings.camera_index)
    except (OSError, ValidationError) as exc:
        logger.warning("Device settings unreadable, using defaults: %s", exc)
        return DeviceSettings(camera_index=settings.camera_index)


def update_device_settings(settings: Settings, **changes) -> DeviceSettings:
    updated = read_device_settings(settings).model_copy(update=changes)
    path = settings.device_settings_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
    return updated


class CameraService:
    def __init__(self, settings: Settings, tracking: TrackingService):
        self._settings = settings
        self._tracking = tracking
        self._scan_lock = threading.Lock()
        self._snapshots: dict[int, bytes] = {}

    def device_settings(self) -> DeviceSettings:
        return read_device_settings(self._settings)

    def preferred_camera(self) -> int:
        return self.device_settings().camera_index

    def set_preferred_camera(self, index: int) -> DeviceSettings:
        return update_device_settings(self._settings, camera_index=index)

    def _worker_camera(self) -> int | None:
        status = self._tracking.status()
        if not status.running:
            return None
        profile, _ = load_profile(self._settings.profiles_dir, status.profile_id)
        if profile is None:
            return None
        return profile.camera_index if profile.camera_index is not None else self.preferred_camera()

    def scan(self) -> list[CameraRead]:
        """Probe every camera. Slow (seconds): call from a worker thread."""
        busy = self._worker_camera()
        with self._scan_lock:
            detector = FaceDetector(self._settings.face_model_path)
            try:
                probes = probe_cameras(detector, skip={busy} if busy is not None else None)
            finally:
                detector.close()
            self._snapshots = {p.index: p.snapshot_jpeg for p in probes if p.snapshot_jpeg}
        preferred = self.preferred_camera()
        return [
            CameraRead(
                index=p.index, available=p.available, in_use=p.index == busy,
                width=p.width, height=p.height, brightness=round(p.brightness, 1),
                face_found=p.face_found, has_snapshot=p.snapshot_jpeg is not None,
                selected=p.index == preferred,
            )
            for p in probes
        ]

    def snapshot(self, index: int) -> bytes | None:
        return self._snapshots.get(index)


@lru_cache
def get_camera_service() -> CameraService:
    return CameraService(get_settings(), get_tracking_service())
