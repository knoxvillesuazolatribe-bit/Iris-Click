"""Gaze Tracking for the hosted website, served by IrisClick Desktop (app/api/routes/desktop_tracking.py)."""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import desktop_link, desktop_tracking
from app.config import get_settings
from app.models.calibration_record import CalibrationRecord
from app.schemas.tracking import WorkerStatusRead

from tests.auth.conftest import make_user  # noqa: F401  (fixture)


class FakeTracking:
    def __init__(self):
        self.running_profile = None
        self.started = []

    def status(self):
        return WorkerStatusRead(running=self.running_profile is not None, pid=1 if self.running_profile else None,
                                profile_id=self.running_profile)

    def start(self, profile_id=None):
        self.started.append(profile_id)
        self.running_profile = profile_id
        return self.status()

    def stop(self):
        self.running_profile = None
        return self.status()


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    tracking = FakeTracking()
    settings = get_settings().model_copy(update={"profiles_dir": tmp_path / "profiles"})
    (tmp_path / "profiles").mkdir()
    monkeypatch.setattr(desktop_tracking, "get_settings", lambda: settings)
    monkeypatch.setattr(desktop_tracking, "get_tracking_service", lambda: tracking)
    monkeypatch.setattr(desktop_link, "session_path", tmp_path / "desktop_session.json")
    monkeypatch.setattr(desktop_tracking, "PUSH_EVERY_S", 0.01)
    app = FastAPI()
    app.include_router(desktop_tracking.router, prefix="/api")
    return TestClient(app), tracking, tmp_path / "profiles"


def link(user_id):
    desktop_link._save_session({"desktop_token": "t", "expires_at": int(time.time()) + 3600,
                                "user": {"user_id": user_id, "full_name": "Ana Cruz"}})


def calibrate(factory, user_id, profiles, file_id="20261107T085500"):
    (profiles / f"{file_id}.json").write_text("{}", encoding="utf-8")
    with factory() as db:
        db.add(CalibrationRecord(user_id=user_id, profile_file_id=file_id, profile_name="Desk",
                                 status="Successful", accuracy_score=95.5))
        db.commit()


def test_needs_a_linked_user_whose_details_have_arrived(desktop, make_user):
    client, _, _ = desktop
    assert client.get("/api/desktop/tracking").json()["detail"] == desktop_tracking.NOT_LINKED
    link(999999)  # linked, but the sync has not copied this user yet
    assert client.get("/api/desktop/tracking").json()["detail"] == desktop_tracking.NOT_READY


def test_without_a_calibration_start_says_calibrate(desktop, make_user):
    client, tracking, _ = desktop
    link(make_user("Ana Cruz"))
    view = client.get("/api/desktop/tracking").json()
    assert view["state"] == "inactive" and view["calibration"] is None
    refused = client.post("/api/desktop/tracking/start")
    assert refused.status_code == 409 and "alibrat" in refused.json()["detail"]
    assert tracking.started == []


def test_start_uses_the_linked_users_own_calibration_and_stop_stops(desktop, make_user, test_database):
    client, tracking, profiles = desktop
    ana = make_user("Ana Cruz")
    ben = make_user("Ben Reyes")
    calibrate(test_database, ben, profiles, "20261107T000000")   # someone else's, newer on disk too
    calibrate(test_database, ana, profiles, "20261107T085500")
    link(ana)
    started = client.post("/api/desktop/tracking/start").json()
    assert tracking.started == ["20261107T085500"]
    assert started["state"] == "active" and started["running_profile_is_mine"] is True
    assert client.post("/api/desktop/tracking/stop").json()["state"] == "inactive"


def test_the_websocket_sends_the_view_every_second(desktop, make_user):
    client, _, _ = desktop
    with client.websocket_connect("/api/ws/tracking") as ws:
        assert ws.receive_json() == {"ok": False, "detail": desktop_tracking.NOT_LINKED}
    link(make_user("Ana Cruz"))
    with client.websocket_connect("/api/ws/tracking") as ws:
        first, second = ws.receive_json(), ws.receive_json()
    assert first["ok"] and first["view"]["state"] == "inactive" and second["ok"]


def test_the_real_pc_server_serves_tracking_to_allowed_websites_only(monkeypatch, tmp_path):
    from starlette.websockets import WebSocketDisconnect
    from app.api import main
    site = "https://iris-click.example.app"
    settings = get_settings().model_copy(update={"cors_origins": [site]})
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(desktop_link, "session_path", tmp_path / "none.json")
    c = TestClient(main.create_app())
    assert c.get("/api/desktop/tracking", headers={"Origin": site}).json()["detail"] == desktop_tracking.NOT_LINKED
    assert c.get("/api/desktop/tracking", headers={"Origin": "https://evil.example.com"}).status_code == 403
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/api/ws/tracking", headers={"Origin": "https://evil.example.com"}) as ws:
            ws.receive_json()
