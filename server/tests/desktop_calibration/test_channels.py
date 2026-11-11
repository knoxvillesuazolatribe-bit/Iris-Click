"""Website and window channels: every message type, versions, origins, reconnects, cancel."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import main
from app.api.routes import desktop_calibration as routes
from app.config import get_settings
from app.desktop_calibration import surface
from app.desktop_calibration.relay import Relay
from app.services import active_user

SITE = "https://iris-click.example.app"
EVIL = "https://evil.example.com"


@pytest.fixture
def env(monkeypatch):
    settings = get_settings().model_copy(update={"cors_origins": [SITE]})
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    spawned, restarted = [], []
    relay = Relay(spawn=lambda port, reason: spawned.append((port, reason)) or 4321,
                  alive=lambda pid: True, restart_tracking=lambda: restarted.append(True),
                  connect_timeout_s=60)
    monkeypatch.setattr(routes, "relay", relay)
    monkeypatch.setattr(routes, "tracking_status", lambda: "stopped")
    monkeypatch.setattr(active_user, "get_user_id", lambda: 7)
    monkeypatch.delenv(surface.ENV_NAME, raising=False)
    client = TestClient(main.create_app())
    client.relay, client.spawned, client.restarted = relay, spawned, restarted
    return client


def site(client):
    return client.websocket_connect("/api/ws/desktop-calibration", headers={"Origin": SITE})


def agent(client):
    return client.websocket_connect("/api/ws/desktop-calibration/agent")


def receive(ws, wanted):
    while True:
        message = ws.receive_json()
        if message["type"] != "tracking.status":
            assert message["type"] == wanted, message
            return message


def test_info_reports_web_by_default_and_desktop_when_set(env, monkeypatch):
    body = env.get("/api/desktop/calibration", headers={"Origin": SITE}).json()
    assert body["v"] == 1 and body["surface"] == "web" and body["linked"] is True
    assert body["state"]["type"] == "calibration.state" and body["state"]["status"] == "idle"
    monkeypatch.setenv(surface.ENV_NAME, "desktop")
    assert env.get("/api/desktop/calibration").json()["surface"] == "desktop"


def test_foreign_websites_are_refused_everywhere(env):
    assert env.get("/api/desktop/calibration", headers={"Origin": EVIL}).status_code == 403
    with pytest.raises(WebSocketDisconnect):
        with env.websocket_connect("/api/ws/desktop-calibration", headers={"Origin": EVIL}) as ws:
            ws.receive_json()


def test_web_pages_cannot_be_the_window_or_open_it(env):
    with pytest.raises(WebSocketDisconnect):
        with env.websocket_connect("/api/ws/desktop-calibration/agent", headers={"Origin": SITE}) as ws:
            ws.receive_json()
    assert env.post("/api/desktop/calibration/open", headers={"Origin": SITE}).status_code == 403
    assert env.spawned == []


def test_local_open_starts_one_window_only(env):
    assert env.post("/api/desktop/calibration/open", json={"reason": "tray"}).json() == {"opened": True}
    assert env.post("/api/desktop/calibration/open", json={"reason": "tray"}).json()["reason"] == "already_open"
    assert len(env.spawned) == 1 and env.spawned[0][1] == "tray"


def test_first_run_opens_only_in_desktop_mode_with_someone_linked(env, monkeypatch):
    assert env.post("/api/desktop/calibration/open", json={"first_run": True}).json() == {
        "opened": False, "reason": "web_mode"}
    monkeypatch.setenv(surface.ENV_NAME, "desktop")
    monkeypatch.setattr(active_user, "get_user_id", lambda: None)
    assert env.post("/api/desktop/calibration/open", json={"first_run": True}).json()["reason"] == "not_linked"
    monkeypatch.setattr(active_user, "get_user_id", lambda: 7)
    assert env.post("/api/desktop/calibration/open", json={"first_run": True}).json() == {"opened": True}


def test_start_needs_someone_linked(env, monkeypatch):
    monkeypatch.setattr(active_user, "get_user_id", lambda: None)
    with site(env) as ws:
        assert receive(ws, "calibration.state")["status"] == "idle"
        ws.send_json({"v": 1, "type": "calibration.start"})
        assert receive(ws, "calibration.error")["reason"] == "not_linked"
    assert env.spawned == []


def test_wrong_version_and_bad_messages_are_refused(env):
    with site(env) as ws:
        receive(ws, "calibration.state")
        ws.send_json({"v": 2, "type": "calibration.start"})
        assert receive(ws, "calibration.error")["reason"] == "version"
        ws.send_json({"v": 1, "type": "calibration.dance"})
        assert receive(ws, "calibration.error")["message"] == "Invalid message."
    assert env.spawned == []


def test_full_run_reaches_the_website_live(env):
    with site(env) as ws:
        receive(ws, "calibration.state")
        ws.send_json({"v": 1, "type": "calibration.start"})
        assert receive(ws, "calibration.state")["status"] == "starting"
        assert env.spawned and env.spawned[0][1] == "website"
        with agent(env) as window:
            window.send_json({"v": 1, "type": "calibration.started", "total": 13})
            assert receive(ws, "calibration.started")["total"] == 13
            window.send_json({"v": 1, "type": "calibration.advice", "kind": "distance", "text": "Move closer."})
            assert receive(ws, "calibration.advice")["text"] == "Move closer."
            window.send_json({"v": 1, "type": "calibration.progress", "done": 7, "total": 13})
            assert receive(ws, "calibration.progress")["done"] == 7

            # A page that reloads mid-calibration catches up at once.
            with site(env) as again:
                state = receive(again, "calibration.state")
                assert (state["status"], state["done"], state["total"]) == ("running", 7, 13)
                assert state["advice"] == {"kind": "distance", "text": "Move closer."}

            window.send_json({"v": 1, "type": "calibration.result", "status": "success",
                              "accuracy_percent": 96.4, "low_accuracy": False, "message": "done"})
            result = receive(ws, "calibration.result")
            assert result["status"] == "success" and result["accuracy_percent"] == 96.4
        assert receive(ws, "calibration.state")["status"] == "idle"
    assert env.restarted == []  # success: the engine already started tracking


def test_cancel_from_the_website_reaches_the_window(env):
    with site(env) as ws:
        receive(ws, "calibration.state")
        ws.send_json({"v": 1, "type": "calibration.start"})
        receive(ws, "calibration.state")
        with agent(env) as window:
            ws.send_json({"v": 1, "type": "calibration.cancel"})
            assert window.receive_json() == {"v": 1, "type": "calibration.cancel"}
            window.send_json({"v": 1, "type": "calibration.cancelled", "reason": "website"})
            assert receive(ws, "calibration.cancelled")["reason"] == "website"
        assert receive(ws, "calibration.state")["status"] == "idle"
    assert env.restarted == [True]  # not calibrated: eye tracking comes back with the old calibration


def test_window_closing_mid_run_is_reported(env):
    with site(env) as ws:
        receive(ws, "calibration.state")
        ws.send_json({"v": 1, "type": "calibration.start"})
        receive(ws, "calibration.state")
        with agent(env) as window:
            window.send_json({"v": 1, "type": "calibration.started", "total": 13})
            receive(ws, "calibration.started")
        assert receive(ws, "calibration.cancelled")["reason"] == "desktop_closed"
        assert receive(ws, "calibration.state")["status"] == "idle"
    assert env.restarted == [True]


def test_only_one_window_connection(env):
    with agent(env):
        with pytest.raises(WebSocketDisconnect):
            with agent(env) as second:
                second.receive_json()


def test_tracking_status_is_pushed(env, monkeypatch):
    monkeypatch.setattr(routes, "tracking_status", lambda: "paused")
    with site(env) as ws:
        seen = {ws.receive_json()["type"], ws.receive_json()["type"]}
    assert seen == {"calibration.state", "tracking.status"}


def test_the_existing_calibration_socket_is_untouched(env):
    # Same path, same first answer as before this feature (no session started here).
    with env.websocket_connect("/api/ws/calibration", headers={"Origin": SITE}) as ws:
        ws.send_json({"type": "collect", "index": 0})
        assert ws.receive_json() == {"type": "error", "message": "Start the calibration first.", "fatal": False}
