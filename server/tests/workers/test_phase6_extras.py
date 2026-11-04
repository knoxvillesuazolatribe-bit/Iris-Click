"""Phase 6 worker additions: edge scroll, both-eye screenshot, Forward / Next Tab."""

import queue
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import select

from app.config import get_settings
from app.core.actions.dwell_click import DwellClicker
from app.core.detection.blink_detector import BOTH, LEFT
from app.core.gaze.estimator import GazeReading
from app.desktop.system_tray import FORWARD, NEXT_TAB
from app.models import database
from app.models.calibration_record import CalibrationRecord
from app.models.screenshot import ScreenshotHistory
from app.models.system_log import SystemLog
from app.models.user import User
from app.services import active_user
from app.workers import extra_keys, tracking_worker
from app.workers.edge_scroll import DOWN, GAP_RESET_S, SCROLL_EVERY_S, UP, EdgeScroller
from app.workers.screenshot_capture import COOLDOWN_S, MAX_CLOSURE_S, UNASSIGNED, ScreenshotTaker
from app.workers.tracking_worker import TrackingWorker

W, H = 1920, 1080


@pytest.fixture
def settings(tmp_path):
    return get_settings().model_copy(update={
        "screenshots_dir": tmp_path / "screenshots", "edge_scroll_enabled": True,
        "edge_scroll_band": 0.08, "dwell_ms": 700})


# --- Edge scroll -----------------------------------------------------------------

class Wheel:
    def __init__(self):
        self.calls = []

    def __call__(self, x, y, notches):
        self.calls.append((x, y, notches))
        return True


def _scroller(settings, exclude=list, **overrides):
    wheel = Wheel()
    scroller = EdgeScroller(settings.model_copy(update=overrides), W, H, exclude=exclude, wheel=wheel)
    return scroller, wheel


def _hold(scroller, x, y, start, seconds, step=0.02):
    """Feeds a steady gaze for ``seconds``; returns the directions scrolled."""
    scrolled, t = [], start
    while t <= start + seconds + 1e-9:
        direction = scroller.update(x, y, t)
        if direction:
            scrolled.append((round(t, 2), direction))
        t += step
    return scrolled


def test_band_is_eight_percent_of_the_height(settings):
    scroller, _ = _scroller(settings)
    assert scroller.band_px == 86
    assert scroller.zone(500, 10) == UP
    assert scroller.zone(500, H - 10) == DOWN
    assert scroller.zone(500, H / 2) is None


def test_no_scroll_before_the_dwell_time(settings):
    scroller, wheel = _scroller(settings)
    assert _hold(scroller, 900, 20, 0.0, 0.68) == []
    assert wheel.calls == []


def test_scrolls_up_at_mid_screen_while_the_gaze_stays(settings):
    scroller, wheel = _scroller(settings)
    scrolled = _hold(scroller, 900, 20, 0.0, 1.5)
    assert scrolled[0][0] == pytest.approx(0.70, abs=0.03)
    assert all(direction == UP for _, direction in scrolled)
    assert len(scrolled) == 1 + int((1.5 - 0.7) / SCROLL_EVERY_S)
    assert wheel.calls[0] == (900, H // 2, 1)  # cursor's x, middle of the screen


def test_bottom_band_scrolls_down(settings):
    scroller, wheel = _scroller(settings)
    _hold(scroller, 300, H - 5, 0.0, 0.8)
    assert wheel.calls == [(300, H // 2, -1)]


def test_leaving_the_band_stops_and_resets_the_dwell(settings):
    scroller, wheel = _scroller(settings)
    _hold(scroller, 900, 20, 0.0, 0.8)
    assert len(wheel.calls) == 1
    assert scroller.update(900, 500, 0.82) is None
    assert _hold(scroller, 900, 20, 0.84, 0.6) == []  # a fresh dwell is needed


def test_a_gap_in_updates_resets_the_dwell(settings):
    """Paused, eyes closed, mouse in use: the worker stops calling update."""
    scroller, wheel = _scroller(settings)
    _hold(scroller, 900, 20, 0.0, 0.6)
    assert _hold(scroller, 900, 20, 0.6 + GAP_RESET_S + 0.05, 0.3) == []
    assert wheel.calls == []


def test_control_bar_is_excluded(settings):
    scroller, wheel = _scroller(settings, exclude=lambda: [(700, 8, 1300, 60)])
    assert _hold(scroller, 900, 30, 0.0, 1.0) == []
    assert _hold(scroller, 200, 30, 2.0, 1.0)  # same band, outside the bar
    assert wheel.calls


def test_disabled_never_scrolls(settings):
    scroller, wheel = _scroller(settings, edge_scroll_enabled=False)
    assert _hold(scroller, 900, 20, 0.0, 2.0) == []
    assert wheel.calls == []


def test_dwell_follows_the_dwell_setting(settings):
    scroller, _ = _scroller(settings, dwell_ms=1200)
    assert _hold(scroller, 900, 20, 0.0, 1.15) == []
    assert _hold(scroller, 900, 20, 1.17, 0.1)


# --- Screenshot ------------------------------------------------------------------

@pytest.fixture
def taker(settings):
    notes = []
    shot = ScreenshotTaker(settings, profile_id="desk", notify=notes.append,
                           grab=lambda: Image.new("RGB", (64, 36), "navy"), background=False)
    shot.notes = notes
    return shot


def _blink(taker, now, closed_for=0.5):
    taker.observe(True, now - closed_for)
    taker.observe(False, now)
    return taker.on_both_blink(now)


def _rows(factory, model):
    with factory() as session:
        return session.scalars(select(model)).all()


def test_short_both_eye_blink_saves_a_screenshot(taker, settings, test_database):
    with test_database() as session:
        user = User(full_name="Ana Cruz", role="assistive_user")
        session.add(user)
        session.flush()
        session.add(CalibrationRecord(user_id=user.user_id, profile_name="Desk",
                                      status="Successful", profile_file_id="desk"))
        session.commit()
        user_id = user.user_id
        calibration_id = session.scalar(select(CalibrationRecord.calibration_id))
    active_user.set_user_id(user_id)

    assert _blink(taker, 10.0) is True
    files = list((settings.screenshots_dir / str(user_id)).glob("*.png"))
    assert len(files) == 1 and Image.open(files[0]).size == (64, 36)
    row = _rows(test_database, ScreenshotHistory)[0]
    assert (row.user_id, row.calibration_id, row.file_name) == (user_id, calibration_id, files[0].name)
    assert [l.activity_type for l in _rows(test_database, SystemLog)] == ["screenshot"]
    assert taker.notes == ["Screenshot saved"]


def test_resting_eyes_take_no_screenshot(taker, settings):
    assert _blink(taker, 10.0, closed_for=MAX_CLOSURE_S + 0.5) is False
    assert not settings.screenshots_dir.exists()


def test_cooldown_between_screenshots(taker):
    assert _blink(taker, 10.0) is True
    assert _blink(taker, 10.0 + COOLDOWN_S - 0.1) is False
    assert _blink(taker, 10.0 + COOLDOWN_S + 0.1) is True


def test_no_signed_in_user_goes_to_unassigned(taker, settings, test_database):
    active_user.set_user_id(None)
    _blink(taker, 10.0)
    assert len(list((settings.screenshots_dir / UNASSIGNED).glob("*.png"))) == 1
    assert _rows(test_database, ScreenshotHistory)[0].user_id is None


def test_user_who_signs_in_later_is_used(taker, settings, make_assistive):
    active_user.set_user_id(None)
    later = make_assistive()
    active_user._write(active_user._path, later)  # written by the server process
    _blink(taker, 10.0)
    assert list((settings.screenshots_dir / str(later)).glob("*.png"))


@pytest.fixture
def make_assistive(test_database):
    def make():
        with test_database() as session:
            user = User(full_name="Ben Reyes", role="assistive_user")
            session.add(user)
            session.commit()
            return user.user_id
    return make


def test_grab_failure_is_reported_not_faked(settings, test_database):
    notes = []

    def broken():
        raise OSError("no screen")

    shot = ScreenshotTaker(settings, notify=notes.append, grab=broken, background=False)
    _blink(shot, 10.0)
    assert notes == ["Screenshot failed: it could not be saved"]
    assert _rows(test_database, ScreenshotHistory) == []


def test_file_is_kept_when_the_database_is_down(taker, settings, monkeypatch):
    def down():
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(database, "get_session_factory", down)
    active_user.set_user_id(None)
    _blink(taker, 10.0)
    assert list((settings.screenshots_dir / UNASSIGNED).glob("*.png"))
    assert taker.notes == ["Screenshot saved (not added to your history)"]


def test_background_save_runs_off_the_tracking_thread(settings, test_database):
    notes = []
    shot = ScreenshotTaker(settings, notify=notes.append,
                           grab=lambda: Image.new("RGB", (8, 8)), background=True)
    _blink(shot, 10.0)
    shot.wait_idle()
    assert notes == ["Screenshot saved"]


# --- Hooks in tracking_worker.py ---------------------------------------------------

class FakeExtras:
    def __init__(self, fail=False):
        self.fail, self.both, self.closures, self.cursor = fail, [], [], []

    def both_blink(self, now):
        if self.fail:
            raise RuntimeError("broken extra")
        self.both.append(now)
        return True


def _blink_host(settings, side, extras):
    return SimpleNamespace(
        blink=SimpleNamespace(update=lambda *_: side),
        settings=settings.model_copy(update={"swap_blink_sides": False,
                                             "right_blink_action": "go_back"}),
        mouse=SimpleNamespace(left_click=lambda *a: calls.append("left_click"),
                              go_back=lambda: calls.append("go_back")),
        dwell=DwellClicker(), paused=False, _wink_point=None, _extras=extras)


calls: list = []


@pytest.fixture(autouse=True)
def _clear_calls():
    calls.clear()


def test_both_eye_blink_hook_calls_the_screenshot(settings):
    extras = FakeExtras()
    TrackingWorker._handle_blink(_blink_host(settings, BOTH, extras), GazeReading(face_found=True))
    assert len(extras.both) == 1
    assert calls == []


def test_a_broken_screenshot_never_breaks_winks(settings):
    broken = FakeExtras(fail=True)
    TrackingWorker._handle_blink(_blink_host(settings, BOTH, broken), GazeReading(face_found=True))
    TrackingWorker._handle_blink(_blink_host(settings, LEFT, broken), GazeReading(face_found=True))
    TrackingWorker._handle_blink(_blink_host(settings, LEFT, None), GazeReading(face_found=True))
    assert calls == ["left_click", "left_click"]


@pytest.mark.parametrize(("command", "keys"), [(FORWARD, ("alt", "right")),
                                               (NEXT_TAB, ("ctrl", "tab"))])
def test_forward_and_next_tab_send_their_keys(settings, monkeypatch, command, keys):
    pressed = []
    monkeypatch.setattr(extra_keys.pyautogui, "hotkey", lambda *k: pressed.append(k))
    commands = queue.Queue()
    commands.put(command)
    quits = []
    host = SimpleNamespace(commands=commands, settings=settings, quit=lambda: quits.append(1))
    TrackingWorker._handle_commands(host)
    assert pressed == [keys]
    assert quits == []


def test_unknown_key_command_does_nothing(monkeypatch):
    pressed = []
    monkeypatch.setattr(extra_keys.pyautogui, "hotkey", lambda *k: pressed.append(k))
    assert extra_keys.press("explode") is False
    assert pressed == []


def test_worker_imports_the_phase6_modules():
    assert tracking_worker.WorkerExtras is not None
    assert tracking_worker.extra_keys is not None
