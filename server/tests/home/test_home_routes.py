"""Home Suite and Gaze Tracking page routes (Phase 3)."""

import os
from datetime import UTC, datetime

import pytest

from app.config import get_settings
from app.schemas.tracking import WorkerStatusRead
from app.services.assistive_service import NO_CALIBRATION, NOT_ON_THIS_COMPUTER
from app.workers.worker_state import LiveState

from tests.auth.conftest import (  # noqa: F401  (fixtures)
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    add_calibration,
    admin_id,
    api,
    fresh_throttle,
    logs,
    make_user,
    profiles_dir,
    signed_in_admin,
)


class FakeTracking:
    """Stands in for the real tracking service: no process is started."""

    def __init__(self):
        self.running, self.profile_id, self.pid = False, None, None
        self.started, self.stops = [], 0

    def status(self):
        return WorkerStatusRead(running=self.running, pid=self.pid, profile_id=self.profile_id,
                                started_at=datetime(2026, 11, 5, tzinfo=UTC) if self.running
                                else None)

    def start(self, profile_id=None):
        if profile_id == "broken":
            raise LookupError("Invalid calibration profile id.")
        self.running, self.profile_id, self.pid = True, profile_id, os.getpid()
        self.started.append(profile_id)
        return self.status()

    def stop(self):
        self.stops += 1
        self.running, self.profile_id, self.pid = False, None, None
        return self.status()


@pytest.fixture
def home_settings(profiles_dir, tmp_path, monkeypatch):
    settings = get_settings().model_copy(update={
        "profiles_dir": profiles_dir,
        "worker_pid_path": tmp_path / "tracking_worker.pid",
        "right_blink_action": "go_back",
        "swap_blink_sides": False,
        "dwell_click_enabled": False,
        "dwell_ms": 700,
        "edge_scroll_enabled": True,
    })
    monkeypatch.setattr("app.api.routes.home.get_settings", lambda: settings)
    return settings


@pytest.fixture
def tracking(monkeypatch):
    fake = FakeTracking()
    monkeypatch.setattr("app.api.routes.home.get_tracking_service", lambda: fake)
    return fake


def _sign_in(api, user_id):
    assert api.post("/api/assistive/select", json={"user_id": user_id}).status_code == 200


def _on_disk(profiles_dir, file_id):
    (profiles_dir / f"{file_id}.json").write_text("{}", encoding="utf-8")


@pytest.fixture
def ana(api, make_user, home_settings, tracking):
    user_id = make_user("Ana Cruz")
    _sign_in(api, user_id)
    return user_id


# --- Access ------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/me/home", "/api/me/tracking"])
def test_signed_out_visitors_are_turned_away(api, home_settings, tracking, path):
    assert api.get(path).status_code == 401


def test_start_and_stop_need_an_assistive_user(signed_in_admin, home_settings, tracking):
    assert signed_in_admin.get("/api/me/home").status_code == 403
    assert signed_in_admin.post("/api/me/tracking/start").status_code == 403
    assert signed_in_admin.post("/api/me/tracking/stop").status_code == 403
    assert tracking.started == [] and tracking.stops == 0


# --- Gesture guide ----------------------------------------------------------

def test_guide_lists_the_default_gestures(api, ana):
    body = api.get("/api/me/home").json()
    assert body["full_name"] == "Ana Cruz"
    assert body["gestures"] == [
        {"gesture": "Look around the screen", "action": "Moves the cursor"},
        {"gesture": "Wink your left eye", "action": "Click"},
        {"gesture": "Wink your right eye", "action": "Go back"},
        {"gesture": "Close both eyes for a moment", "action": "Takes a screenshot"},
        {"gesture": "Look at the top or bottom edge", "action": "Scrolls up or down"},
    ]


def test_guide_leaves_out_edge_scroll_when_off(api, ana, home_settings, monkeypatch):
    off = home_settings.model_copy(update={"edge_scroll_enabled": False})
    monkeypatch.setattr("app.api.routes.home.get_settings", lambda: off)
    gestures = [g["gesture"] for g in api.get("/api/me/home").json()["gestures"]]
    assert "Look at the top or bottom edge" not in gestures
    assert "Close both eyes for a moment" in gestures


def test_guide_follows_the_real_settings(api, ana, home_settings, monkeypatch):
    changed = home_settings.model_copy(update={
        "right_blink_action": "undo", "swap_blink_sides": True,
        "dwell_click_enabled": True, "dwell_ms": 700})
    monkeypatch.setattr("app.api.routes.home.get_settings", lambda: changed)
    gestures = {g["gesture"]: g["action"] for g in api.get("/api/me/home").json()["gestures"]}
    assert gestures["Wink your left eye"] == "Undo"
    assert gestures["Wink your right eye"] == "Click"
    assert gestures["Keep looking at one spot"] == "Clicks after 0.7 seconds"


# --- Tracking view -----------------------------------------------------------

def test_inactive_without_calibration(api, ana):
    view = api.get("/api/me/tracking").json()
    assert view["state"] == "inactive"
    assert view["calibration"] is None
    assert view["calibration_unavailable_reason"] == NO_CALIBRATION


def test_calibration_missing_from_this_computer(api, ana, test_database):
    add_calibration(test_database, ana, file_id="gone")
    view = api.get("/api/me/tracking").json()
    assert view["calibration_unavailable_reason"] == NOT_ON_THIS_COMPUTER


def test_shows_the_users_calibration(api, ana, test_database, profiles_dir):
    add_calibration(test_database, ana, file_id="desk", accuracy="93.25")
    _on_disk(profiles_dir, "desk")
    calibration = api.get("/api/me/tracking").json()["calibration"]
    assert calibration["profile_id"] == "desk"
    assert calibration["profile_name"] == "Desk"
    assert float(calibration["accuracy_score"]) == 93.25


# --- Start / Stop ------------------------------------------------------------

def test_start_without_calibration_is_refused(api, ana, tracking):
    response = api.post("/api/me/tracking/start")
    assert response.status_code == 409
    assert response.json()["detail"] == NO_CALIBRATION
    assert tracking.started == []


def test_start_uses_the_users_own_latest_calibration(api, ana, make_user, test_database,
                                                     profiles_dir, tracking):
    other = make_user("Ben Reyes")
    add_calibration(test_database, ana, file_id="old", when=datetime(2026, 1, 1, tzinfo=UTC))
    add_calibration(test_database, ana, file_id="new", when=datetime(2026, 6, 1, tzinfo=UTC))
    add_calibration(test_database, other, file_id="bens", when=datetime(2026, 10, 1, tzinfo=UTC))
    for file_id in ("old", "new", "bens"):
        _on_disk(profiles_dir, file_id)

    view = api.post("/api/me/tracking/start").json()
    assert tracking.started == ["new"]
    assert view["state"] == "active"
    assert view["running_profile_is_mine"] is True
    assert view["calibration"]["profile_id"] == "new"

    api.post("/api/me/tracking/start")  # already running: nothing new to log
    started = logs(test_database, "tracking_started")
    assert len(started) == 1
    assert started[0].user_id == ana


def test_start_failure_shows_the_real_reason(api, ana, test_database, profiles_dir):
    add_calibration(test_database, ana, file_id="broken")
    _on_disk(profiles_dir, "broken")
    response = api.post("/api/me/tracking/start")
    assert response.status_code == 409
    assert "Invalid calibration profile id." in response.json()["detail"]
    assert logs(test_database, "tracking_started") == []


def test_stop_is_logged_only_when_tracking_was_running(api, ana, test_database, profiles_dir,
                                                       tracking):
    api.post("/api/me/tracking/stop")
    assert logs(test_database, "tracking_stopped") == []
    add_calibration(test_database, ana, file_id="desk")
    _on_disk(profiles_dir, "desk")
    api.post("/api/me/tracking/start")
    view = api.post("/api/me/tracking/stop").json()
    assert view["state"] == "inactive"
    assert len(logs(test_database, "tracking_stopped")) == 1


def test_someone_elses_tracking_is_reported(api, ana, test_database, profiles_dir, tracking):
    add_calibration(test_database, ana, file_id="desk")
    _on_disk(profiles_dir, "desk")
    tracking.start("someone-else")
    view = api.get("/api/me/tracking").json()
    assert view["state"] == "active"
    assert view["running_profile_is_mine"] is False
    assert view["calibration"]["profile_id"] == "desk"


# --- Live status -------------------------------------------------------------

def test_live_status_paused_gaze_and_winks(api, ana, home_settings, tracking):
    tracking.start("someone-else")
    live = LiveState(home_settings)
    live.note_gaze(960, 540, 1920, 1080)
    live.note_wink("left")
    live.note_status("Paused.", "paused", True)
    live._write(force=True)
    view = api.get("/api/me/tracking").json()
    assert view["state"] == "paused"
    assert view["status_text"] == "Paused."
    assert view["live"]["gaze"] == {"x": 960, "y": 540, "screen_w": 1920, "screen_h": 1080}
    assert view["live"]["winks"] == {"left": 1, "right": 0}


def test_no_live_status_still_shows_active(api, ana, tracking):
    tracking.start("someone-else")
    view = api.get("/api/me/tracking").json()
    assert view["state"] == "active"
    assert view["live"] is None
