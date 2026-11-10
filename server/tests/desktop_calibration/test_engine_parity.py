"""The desktop window drives the SAME engine as the website: same socket, same session,
same saved profile, same failure records. Only the client differs."""

import json

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config import get_settings
from app.core.calibration import collector as collector_module
from app.core.calibration.collector import CALIBRATION_POINTS
from app.core.calibration.profile import load_profile
from app.desktop_calibration import flow as F
from app.services import calibration_service
from app.services.camera_service import CameraService
from app.services.tracking_service import get_tracking_service

from tests.api.test_calibration_ws import FakeTracker, FakeTrackingService


@pytest.fixture
def engine(tmp_path, monkeypatch):
    FakeTracker.instances.clear()
    monkeypatch.setattr(calibration_service, "GazeTracker", FakeTracker)
    monkeypatch.setattr(collector_module, "COLLECT_MS", 60)
    monkeypatch.setattr(collector_module, "MAX_COLLECT_MS", 400)
    records = {"success": [], "failure": []}
    monkeypatch.setattr(calibration_service.calibration_records, "record_success",
                        lambda profile: records["success"].append(profile))
    monkeypatch.setattr(calibration_service.calibration_records, "record_failure",
                        lambda *a, **k: records["failure"].append(a))
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
    with TestClient(create_app()) as client:
        client.tracking, client.records, client.dir = tracking, records, tmp_path
        yield client


def drive_desktop(ws, closed_eyes=False):
    """Runs the window's flow against the real socket with a fast fake clock."""
    t = 1.0
    flow = F.CalibrationFlow("Desktop 2026-11-10 09:00", (1920, 1080), t)
    flow.connected(t)
    for message in flow.take_outgoing():
        ws.send_json(message)
    while flow.phase not in (F.SUCCESS, F.FAILED):
        message = ws.receive_json()
        flow.on_message(message, t)
        if message["type"] == "ready":
            tracker = FakeTracker.instances[-1]
            tracker.closed_eyes = closed_eyes
            flow.key("enter", t)  # helper starts at once
            flow.key("enter", t)  # and skips the countdown
        t += 0.5
        flow.tick(t)
        for out in flow.take_outgoing():
            if out["type"] == "collect":
                FakeTracker.instances[-1].target = flow.points[out["index"]]
            ws.send_json(out)
    return flow


def drive_web(ws):
    """What the website's calibration page sends (see tests/api/test_calibration_ws.py)."""
    ws.send_json({"type": "start", "profile_name": "Desk", "screen": {"width": 1920, "height": 1080}})
    while (ready := ws.receive_json())["type"] != "ready":
        pass
    tracker = FakeTracker.instances[-1]
    for index, point in enumerate(ready["points"]):
        tracker.target = (point["x"], point["y"])
        ws.send_json({"type": "collect", "index": index})
        while ws.receive_json()["type"] != "point_result":
            pass
    while (result := ws.receive_json())["type"] != "result":
        pass
    return result


def saved(directory):
    files = sorted(directory.glob("*.json"))
    return [json.loads(f.read_text("utf-8")) for f in files]


def test_desktop_flow_saves_the_same_profile_as_the_website(engine):
    with engine.websocket_connect("/api/ws/calibration") as ws:
        flow = drive_desktop(ws)
    assert flow.phase == F.SUCCESS
    assert flow.total == len(CALIBRATION_POINTS) == 13
    assert flow.result["accuracy_percent"] is not None
    desktop_profile = saved(engine.dir)[0]
    assert desktop_profile["profile_name"].startswith("Desktop ")
    assert engine.tracking.calls == ["stop", ("start", desktop_profile["id"])]  # tracking starts as today

    with engine.websocket_connect("/api/ws/calibration") as ws:
        web_result = drive_web(ws)
    assert web_result["status"] == "success"
    web_profile = next(p for p in saved(engine.dir) if p["id"] != desktop_profile["id"])

    # Same engine, same fields, same thresholds; only the person's name for it differs.
    assert set(desktop_profile) == set(web_profile)
    # Both load as usable calibrations (the model's inner keys depend on the gaze source
    # the engine picked from the random fake readings, not on which client ran it).
    for profile in (desktop_profile, web_profile):
        loaded, model = load_profile(engine.dir, profile["id"])
        assert loaded is not None and model is not None
    assert desktop_profile["screen"] == web_profile["screen"] == {"width": 1920, "height": 1080}
    assert len(engine.records["success"]) == 2


def test_desktop_failure_is_recorded_like_the_website(engine):
    with engine.websocket_connect("/api/ws/calibration") as ws:
        flow = drive_desktop(ws, closed_eyes=True)
    assert flow.phase == F.FAILED
    assert flow.result["status"] == "failed"
    assert engine.records["failure"] and engine.records["failure"][0][1] == "dot_not_clear"
    assert ("start", None) not in engine.tracking.calls
    assert saved(engine.dir) == []
