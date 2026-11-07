"""The tracking worker loads the signed-in user's settings at start (H4d, Phase 7)."""

import time
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.core.actions.dwell_click import DwellClicker
from app.core.detection.blink_detector import LEFT, RIGHT
from app.core.gaze.estimator import GazeReading
from app.models import database
from app.models.accessibility_settings import AccessibilitySettings
from app.models.user import User
from app.services import active_user
from app.workers import tracking_worker, user_settings
from app.workers.tracking_worker import TrackingWorker


@pytest.fixture
def base():
    return get_settings().model_copy(update={
        "dwell_click_enabled": False, "dwell_ms": 700, "cursor_smoothing": 0.25,
        "blink_click_enabled": True, "blink_threshold": 0.18, "edge_scroll_enabled": True})


@pytest.fixture
def ana(test_database):
    with test_database() as session:
        user = User(full_name="Ana Cruz", role="assistive_user")
        session.add(user)
        session.commit()
        user_id = user.user_id
    active_user.set_user_id(user_id)
    return user_id


def _save(factory, user_id, **values):
    with factory() as session:
        session.add(AccessibilitySettings(user_id=user_id, **values))
        session.commit()


def test_signed_out_uses_env(base):
    active_user.set_user_id(None)
    assert user_settings.for_active_user(base) is base


def test_user_without_saved_settings_uses_env(base, ana):
    assert user_settings.for_active_user(base) is base


def test_saved_settings_are_used(base, ana, test_database):
    _save(test_database, ana, dwell_enabled=True, dwell_ms=1100, cursor_smoothing=0.45,
          blink_to_click=False, blink_sensitivity=0.22, edge_scroll_enabled=False)
    loaded = user_settings.for_active_user(base)
    assert (loaded.dwell_click_enabled, loaded.dwell_ms, loaded.cursor_smoothing,
            loaded.blink_click_enabled, loaded.blink_threshold, loaded.edge_scroll_enabled) == (
        True, 1100, 0.45, False, 0.22, False)
    # Everything else still comes from .env.
    assert loaded.right_blink_action == base.right_blink_action
    assert loaded.profiles_dir == base.profiles_dir


def test_a_row_with_no_way_to_click_keeps_wink_click(base, ana, test_database):
    _save(test_database, ana, dwell_enabled=False, blink_to_click=False)
    assert user_settings.for_active_user(base).blink_click_enabled is True


def test_database_errors_fall_back_to_env(base, ana, monkeypatch):
    def down():
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(database, "get_session_factory", down)
    assert user_settings.for_active_user(base) is base


def test_slow_database_falls_back_to_env(base, ana, monkeypatch):
    def slow():
        time.sleep(1.0)
        raise RuntimeError("too late")

    monkeypatch.setattr(database, "get_session_factory", slow)
    started = time.monotonic()
    assert user_settings.for_active_user(base, timeout_s=0.2) is base
    assert time.monotonic() - started < 0.8


def test_worker_main_calls_the_loader(monkeypatch):
    seen = []

    def loader(settings):
        seen.append(settings)
        raise RuntimeError("loader broke")  # must not stop tracking from starting

    monkeypatch.setattr(tracking_worker, "configure_logging", lambda s: None)
    monkeypatch.setattr(tracking_worker, "enable_dpi_awareness", lambda: None)
    monkeypatch.setattr(tracking_worker.user_settings, "for_active_user", loader)
    monkeypatch.setattr(tracking_worker, "load_profile", lambda *a: (None, None))
    monkeypatch.setattr(tracking_worker.webbrowser, "open", lambda url: None)
    assert tracking_worker.main([]) == 2  # carried on to the (missing) profile check
    assert len(seen) == 1


# --- Wink-to-click hook -------------------------------------------------------------------

def _blink_host(settings, side):
    calls = []
    host = SimpleNamespace(
        blink=SimpleNamespace(update=lambda *_: side), settings=settings,
        mouse=SimpleNamespace(left_click=lambda *a: calls.append("left_click"),
                              go_back=lambda: calls.append("go_back")),
        dwell=DwellClicker(), paused=False, _wink_point=None)
    host.calls = calls
    return host


def test_wink_click_off_ignores_left_wink_but_keeps_back(base):
    off = base.model_copy(update={"blink_click_enabled": False, "dwell_click_enabled": True,
                                  "swap_blink_sides": False, "right_blink_action": "go_back"})
    left, right = _blink_host(off, LEFT), _blink_host(off, RIGHT)
    TrackingWorker._handle_blink(left, GazeReading(face_found=True))
    TrackingWorker._handle_blink(right, GazeReading(face_found=True))
    assert left.calls == [] and right.calls == ["go_back"]


def test_wink_click_on_by_default(base):
    host = _blink_host(base.model_copy(update={"swap_blink_sides": False}), LEFT)
    TrackingWorker._handle_blink(host, GazeReading(face_found=True))
    assert host.calls == ["left_click"]
