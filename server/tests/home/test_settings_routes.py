"""Accessibility Settings routes, gesture guide and restart (Phase 7)."""

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models.accessibility_settings import AccessibilitySettings
from app.services import accessibility_service

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
from tests.home.test_home_routes import FakeTracking

STANDARD = {"dwell_enabled": False, "dwell_ms": 700, "smoothing": "medium", "blink_to_click": True,
            "blink_sensitivity": 3, "edge_scroll_enabled": True, "voice_volume": 100}
MINE = {"dwell_enabled": True, "dwell_ms": 1100, "smoothing": "high", "blink_to_click": False,
        "blink_sensitivity": 5, "edge_scroll_enabled": False, "voice_volume": 60}


@pytest.fixture
def base(profiles_dir, tmp_path, monkeypatch):
    settings = get_settings().model_copy(update={
        "profiles_dir": profiles_dir, "worker_pid_path": tmp_path / "tracking_worker.pid",
        "dwell_click_enabled": False, "dwell_ms": 700, "cursor_smoothing": 0.25,
        "blink_click_enabled": True, "blink_threshold": 0.18, "edge_scroll_enabled": True,
        "right_blink_action": "go_back", "swap_blink_sides": False})
    for module in ("accessibility", "home"):
        monkeypatch.setattr(f"app.api.routes.{module}.get_settings", lambda: settings)
    return settings


@pytest.fixture
def tracking(monkeypatch):
    fake = FakeTracking()
    monkeypatch.setattr("app.api.routes.home.get_tracking_service", lambda: fake)
    return fake


@pytest.fixture
def ana(api, make_user, base, tracking):
    user_id = make_user("Ana Cruz")
    assert api.post("/api/assistive/select", json={"user_id": user_id}).status_code == 200
    return user_id


def _values(body):
    return {k: body[k] for k in STANDARD}


def _row(factory, user_id):
    with factory() as session:
        return session.scalar(select(AccessibilitySettings).where(AccessibilitySettings.user_id == user_id))


# --- Access ------------------------------------------------------------------------

def test_signed_out_and_admins_are_turned_away(api, signed_in_admin, base):
    assert signed_in_admin.get("/api/me/settings").status_code == 403
    assert signed_in_admin.put("/api/me/settings", json=MINE).status_code == 403
    signed_in_admin.post("/api/auth/logout")
    assert api.get("/api/me/settings").status_code == 401


# --- Reading and saving ---------------------------------------------------------------

def test_new_user_sees_the_standard_settings(api, ana, test_database):
    body = api.get("/api/me/settings").json()
    assert _values(body) == STANDARD
    assert body["is_default"] is True
    assert body["defaults"] == STANDARD
    assert _row(test_database, ana) is None


def test_save_stores_real_values_and_logs(api, ana, test_database):
    body = api.put("/api/me/settings", json=MINE).json()
    assert _values(body) == MINE and body["is_default"] is False
    row = _row(test_database, ana)
    assert (row.dwell_enabled, row.dwell_ms, row.cursor_smoothing, row.blink_to_click,
            row.blink_sensitivity, row.edge_scroll_enabled, row.voice_volume) == (
        True, 1100, 0.45, False, 0.22, False, 60)
    assert "saved by Ana Cruz" in logs(test_database, "settings_updated")[0].activity_description


def test_saving_again_updates_the_same_row(api, ana, test_database):
    api.put("/api/me/settings", json=MINE)
    api.put("/api/me/settings", json={**MINE, "dwell_ms": 400})
    with test_database() as session:
        rows = session.scalars(select(AccessibilitySettings)).all()
    assert len(rows) == 1 and rows[0].dwell_ms == 400


def test_wink_and_dwell_cannot_both_be_off(api, ana, test_database):
    response = api.put("/api/me/settings", json={**MINE, "dwell_enabled": False})
    assert response.status_code == 422
    assert response.json()["detail"] == accessibility_service.NO_WAY_TO_CLICK
    assert _row(test_database, ana) is None


@pytest.mark.parametrize(("field", "value"), [
    ("dwell_ms", 399), ("dwell_ms", 1501), ("blink_sensitivity", 0), ("blink_sensitivity", 6),
    ("voice_volume", -1), ("voice_volume", 101), ("smoothing", "turbo"),
])
def test_out_of_range_values_are_refused(api, ana, field, value):
    assert api.put("/api/me/settings", json={**MINE, field: value}).status_code == 422


def test_reset_returns_to_the_standard_settings(api, ana, test_database):
    api.put("/api/me/settings", json=MINE)
    body = api.post("/api/me/settings/reset").json()
    assert _values(body) == STANDARD and body["is_default"] is True
    assert _row(test_database, ana) is None
    assert len(logs(test_database, "settings_reset")) == 1


def test_each_user_has_their_own_settings(api, ana, make_user):
    api.put("/api/me/settings", json=MINE)
    ben = make_user("Ben Reyes")
    api.post("/api/assistive/select", json={"user_id": ben})
    assert _values(api.get("/api/me/settings").json()) == STANDARD


def test_odd_env_values_map_to_the_nearest_step(base):
    odd = base.model_copy(update={"cursor_smoothing": 0.4, "blink_threshold": 0.15, "dwell_ms": 2000})
    values = accessibility_service.defaults(odd)
    assert (values.smoothing, values.blink_sensitivity, values.dwell_ms) == ("high", 1, 1500)


# --- Gesture guide follows the user's settings ------------------------------------------

def _guide(api):
    return {g["gesture"]: g["action"] for g in api.get("/api/me/home").json()["gestures"]}


def test_guide_follows_saved_settings(api, ana):
    assert "Wink your left eye" in _guide(api)
    api.put("/api/me/settings", json=MINE)  # wink-click off, dwell on 1.1 s, edge off
    guide = _guide(api)
    assert "Wink your left eye" not in guide
    assert guide["Wink your right eye"] == "Go back"
    assert guide["Keep looking at one spot"] == "Clicks after 1.1 seconds"
    assert "Look at the top or bottom edge" not in guide


# --- Restart ----------------------------------------------------------------------------

def test_restart_uses_my_calibration_and_logs(api, ana, test_database, profiles_dir, tracking):
    add_calibration(test_database, ana, file_id="desk")
    (profiles_dir / "desk.json").write_text("{}", encoding="utf-8")
    tracking.start("desk")
    view = api.post("/api/me/tracking/restart").json()
    assert view["state"] == "active"
    assert tracking.stops == 1 and tracking.started == ["desk", "desk"]
    assert len(logs(test_database, "tracking_restarted")) == 1


def test_restart_without_calibration_changes_nothing(api, ana, tracking):
    tracking.start("someone-else")
    response = api.post("/api/me/tracking/restart")
    assert response.status_code == 409
    assert tracking.stops == 0 and tracking.running


def test_failed_restart_says_so(api, ana, test_database, profiles_dir, tracking):
    add_calibration(test_database, ana, file_id="broken")
    (profiles_dir / "broken.json").write_text("{}", encoding="utf-8")
    response = api.post("/api/me/tracking/restart")
    assert response.status_code == 409
    assert "could not start again" in response.json()["detail"]
    assert not tracking.running
