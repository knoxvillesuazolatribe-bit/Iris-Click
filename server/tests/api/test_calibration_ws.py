import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config import get_settings
from app.core.calibration import collector as collector_module
from app.core.calibration.collector import CALIBRATION_POINTS
from app.services import calibration_service
from app.services.camera_service import CameraService
from app.services.tracking_service import get_tracking_service

from tests.factories import synthetic_reading


class FakeTracker:
    """Stands in for the webcam: readings follow whichever dot is shown."""

    instances = []

    def __init__(self, *args, camera_index=0, **kwargs):
        self.camera_index = camera_index
        self.target = CALIBRATION_POINTS[0]
        self.deep_gaze_available = True
        self.last_error = None
        self.stopped = False
        self.closed_eyes = False
        self._rng = np.random.default_rng(3)
        FakeTracker.instances.append(self)

    def start(self):
        pass

    def stop(self):
        self.stopped = True

    def read(self):
        ear = 0.02 if self.closed_eyes else 0.3
        return synthetic_reading(self.target, self._rng, left_ear=ear, right_ear=ear)


class FakeTrackingService:
    def __init__(self):
        self.calls = []

    def stop(self):
        self.calls.append("stop")

    def start(self, profile_id=None):
        self.calls.append(("start", profile_id))


@pytest.fixture
def client(tmp_path, monkeypatch):
    FakeTracker.instances.clear()
    monkeypatch.setattr(calibration_service, "GazeTracker", FakeTracker)
    monkeypatch.setattr(collector_module, "COLLECT_MS", 60)
    monkeypatch.setattr(collector_module, "MAX_COLLECT_MS", 400)
    settings = get_settings().model_copy(update={
        "profiles_dir": tmp_path,
        "device_settings_path": tmp_path / "device" / "device_settings.json",
    })
    tracking = FakeTrackingService()
    monkeypatch.setattr("app.api.websocket.calibration_ws.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.websocket.calibration_ws.get_tracking_service", lambda: tracking)
    cameras = CameraService(settings, tracking)
    monkeypatch.setattr("app.api.websocket.calibration_ws.get_camera_service", lambda: cameras)
    get_tracking_service.cache_clear()
    with TestClient(create_app()) as test_client:
        test_client.tracking = tracking
        test_client.cameras = cameras
        yield test_client


def _receive(ws, wanted):
    while True:
        message = ws.receive_json()
        if message["type"] != "frame_status":
            assert message["type"] == wanted, message
            return message


def _start(ws, **extra):
    ws.send_json({"type": "start", "profile_name": "Desk",
                  "screen": {"width": 1920, "height": 1080}, **extra})
    return _receive(ws, "ready")


def test_full_calibration_saves_profile_and_starts_worker(client, tmp_path):
    with client.websocket_connect("/api/ws/calibration") as ws:
        ready = _start(ws)
        assert len(ready["points"]) == len(CALIBRATION_POINTS)
        tracker = FakeTracker.instances[-1]

        for index, point in enumerate(ready["points"]):
            tracker.target = (point["x"], point["y"])
            ws.send_json({"type": "collect", "index": index})
            assert _receive(ws, "point_result")["status"] == "accepted"

        result = _receive(ws, "result")

    assert result["status"] == "success", result
    assert result["worker_started"] is True
    assert result["profile"]["profile_name"] == "Desk"
    assert "model" not in result["profile"]
    assert tracker.stopped
    assert client.tracking.calls == ["stop", ("start", result["profile"]["id"])]
    assert len(list(tmp_path.glob("*.json"))) == 1

    latest = client.get("/api/calibration-profiles")
    assert latest.status_code == 200


def test_unclear_dot_is_retried_then_fails(client):
    with client.websocket_connect("/api/ws/calibration") as ws:
        _start(ws)
        tracker = FakeTracker.instances[-1]
        tracker.closed_eyes = True

        ws.send_json({"type": "collect", "index": 0})
        assert _receive(ws, "point_result")["status"] == "retry"
        ws.send_json({"type": "collect", "index": 0})
        assert _receive(ws, "point_result")["status"] == "failed"
        result = _receive(ws, "result")

    assert result["status"] == "failed"
    assert tracker.stopped
    assert ("start", None) not in client.tracking.calls


def test_out_of_order_dot_is_refused(client):
    with client.websocket_connect("/api/ws/calibration") as ws:
        _start(ws)
        ws.send_json({"type": "collect", "index": 3})
        assert "Expected dot 1" in _receive(ws, "error")["message"]


def test_invalid_message_is_reported(client):
    with client.websocket_connect("/api/ws/calibration") as ws:
        ws.send_json({"type": "start", "profile_name": "", "screen": {"width": 0, "height": 0}})
        assert _receive(ws, "error")["fatal"] is False


def test_chosen_camera_is_used_remembered_and_saved_in_profile(client):
    with client.websocket_connect("/api/ws/calibration") as ws:
        ready = _start(ws, camera_index=2)
        tracker = FakeTracker.instances[-1]
        assert tracker.camera_index == 2
        for index, point in enumerate(ready["points"]):
            tracker.target = (point["x"], point["y"])
            ws.send_json({"type": "collect", "index": index})
            _receive(ws, "point_result")
        result = _receive(ws, "result")

    assert result["profile"]["camera_index"] == 2
    assert client.cameras.preferred_camera() == 2


def test_without_a_choice_the_remembered_camera_is_used(client):
    client.cameras.set_preferred_camera(1)
    with client.websocket_connect("/api/ws/calibration") as ws:
        _start(ws)
        assert FakeTracker.instances[-1].camera_index == 1
