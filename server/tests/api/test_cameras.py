import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config import get_settings
from app.core.camera.discovery import CameraProbe
from app.schemas.tracking import WorkerStatusRead
from app.services import camera_service
from app.services.camera_service import CameraService

JPEG = b"\xff\xd8fake-jpeg\xff\xd9"


class IdleTracking:
    def status(self):
        return WorkerStatusRead(running=False)


class NoopDetector:
    def __init__(self, *_args):
        pass

    def close(self):
        pass


@pytest.fixture
def cameras(tmp_path, monkeypatch):
    settings = get_settings().model_copy(update={
        "profiles_dir": tmp_path, "device_settings_path": tmp_path / "device_settings.json",
    })
    service = CameraService(settings, IdleTracking())
    monkeypatch.setattr(camera_service, "FaceDetector", NoopDetector)
    monkeypatch.setattr(camera_service, "probe_cameras", lambda _detector, skip=None: [
        CameraProbe(index=0, available=True, width=1280, height=720, brightness=140,
                    face_found=True, snapshot_jpeg=JPEG),
        CameraProbe(index=1, available=True, width=640, height=480, brightness=45,
                    face_found=False, snapshot_jpeg=JPEG),
    ])
    monkeypatch.setattr("app.api.routes.cameras.get_camera_service", lambda: service)
    return service


def test_lists_cameras_with_face_status_and_selection(cameras):
    cameras.set_preferred_camera(1)
    with TestClient(create_app()) as client:
        body = client.get("/api/cameras").json()

    assert [c["index"] for c in body] == [0, 1]
    assert body[0]["face_found"] is True and body[0]["selected"] is False
    assert body[1]["selected"] is True and body[1]["has_snapshot"] is True


def test_snapshot_served_without_caching(cameras):
    with TestClient(create_app()) as client:
        client.get("/api/cameras")
        response = client.get("/api/cameras/0/snapshot")
        missing = client.get("/api/cameras/5/snapshot")

    assert response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"
    assert missing.status_code == 404


def test_preferred_camera_defaults_to_env_setting(cameras):
    assert cameras.preferred_camera() == get_settings().camera_index
