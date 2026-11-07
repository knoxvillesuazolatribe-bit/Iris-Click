"""Live status the tracking worker shares with the Gaze Tracking page (Phase 3)."""

import json
import os
import queue
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.core.detection.blink_detector import BOTH, LEFT, RIGHT
from app.core.actions.dwell_click import DwellClicker
from app.core.gaze.estimator import GazeReading
from app.desktop.system_tray import HOME
from app.workers import tracking_worker
from app.workers.tracking_worker import TrackingWorker
from app.workers.worker_state import (
    GAZE_FRESH_S,
    STALE_AFTER_S,
    WRITE_EVERY_S,
    LiveState,
    read_state,
    state_path,
)


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def settings(tmp_path):
    return get_settings().model_copy(update={"worker_pid_path": tmp_path / "tracking_worker.pid"})


def _saved(settings):
    return json.loads(state_path(settings).read_text("utf-8"))


def test_state_file_sits_next_to_the_pid_file(settings, tmp_path):
    assert state_path(settings) == tmp_path / "tracking_worker_state.json"


def test_status_writes_are_throttled(settings):
    clock = Clock()
    live = LiveState(settings, clock=clock)
    live.note_status("Tracking", "tracking", False)
    live.note_status("Paused.", "paused", True)
    assert _saved(settings)["status"] == "Tracking"
    clock.now += WRITE_EVERY_S
    live.note_status("Paused.", "paused", True)
    saved = _saved(settings)
    assert (saved["status"], saved["kind"], saved["paused"]) == ("Paused.", "paused", True)
    assert saved["pid"] == os.getpid()


def test_winks_are_counted_and_written_at_once(settings):
    clock = Clock()
    live = LiveState(settings, clock=clock)
    live.note_status("Tracking", "tracking", False)
    live.note_wink(LEFT)
    live.note_wink(LEFT)
    live.note_wink(RIGHT)
    live.note_wink(BOTH)
    assert _saved(settings)["winks"] == {"left": 2, "right": 1}


def test_gaze_position_is_saved(settings):
    clock = Clock()
    live = LiveState(settings, clock=clock)
    live.note_gaze(812.6, 400.2, 1920, 1080)
    gaze = _saved(settings)["gaze"]
    assert (gaze["x"], gaze["y"], gaze["screen_w"], gaze["screen_h"]) == (813, 400, 1920, 1080)


def test_a_failed_write_never_raises(tmp_path):
    settings = get_settings().model_copy(
        update={"worker_pid_path": tmp_path / "missing" / "tracking_worker.pid"})
    live = LiveState(settings)
    live.note_status("Tracking", "tracking", False)
    live.note_wink(LEFT)
    assert not state_path(settings).exists()


def test_read_state_returns_fresh_data_for_the_running_worker(settings):
    clock = Clock()
    live = LiveState(settings, clock=clock)
    live.note_gaze(10, 20, 1920, 1080)
    live.note_wink(RIGHT)
    state = read_state(state_path(settings), os.getpid(), now=clock.now + 1)
    assert state["gaze"]["x"] == 10
    assert state["winks"] == {"left": 0, "right": 1}


def test_read_state_ignores_old_workers_stale_data_and_bad_files(settings):
    path = state_path(settings)
    clock = Clock()
    LiveState(settings, clock=clock).note_status("Tracking", "tracking", False)
    assert read_state(path, os.getpid() + 1, now=clock.now) is None
    assert read_state(path, os.getpid(), now=clock.now + STALE_AFTER_S + 0.1) is None
    path.write_text("not json", encoding="utf-8")
    assert read_state(path, os.getpid(), now=clock.now) is None
    assert read_state(path.with_name("nothing.json"), os.getpid()) is None


def test_old_gaze_is_dropped(settings):
    clock = Clock()
    live = LiveState(settings, clock=clock)
    live.note_gaze(10, 20, 1920, 1080)
    clock.now += GAZE_FRESH_S + 0.1
    live.note_status("Face not visible", "problem", False)
    state = read_state(state_path(settings), os.getpid(), now=clock.now)
    assert state is not None and state["gaze"] is None


# --- Hooks in tracking_worker.py ---------------------------------------------

def _status_host(settings, paused=False, live=True):
    host = SimpleNamespace(
        bar=SimpleNamespace(set_state=lambda *_: None),
        tray=SimpleNamespace(set_state=lambda *_: None),
        voice=SimpleNamespace(enabled=True),
        paused=paused,
    )
    if live:
        host._live = LiveState(settings)
    return host


def test_set_status_hook_shares_paused_state(settings):
    host = _status_host(settings, paused=True)
    TrackingWorker._set_status(host, "Paused.", "paused")
    assert _saved(settings)["paused"] is True


def test_hooks_do_nothing_without_live_state(settings):
    TrackingWorker._set_status(_status_host(settings, live=False), "Tracking", "tracking")
    assert not state_path(settings).exists()


def test_wink_hook_counts_and_still_clicks(settings):
    calls = []
    host = SimpleNamespace(
        blink=SimpleNamespace(update=lambda *_: LEFT), settings=settings,
        mouse=SimpleNamespace(left_click=lambda *a: calls.append("left_click")),
        dwell=DwellClicker(), paused=False, _wink_point=None, _live=LiveState(settings))
    TrackingWorker._handle_blink(host, GazeReading(face_found=True))
    assert calls == ["left_click"]
    assert _saved(settings)["winks"] == {"left": 1, "right": 0}


def test_wink_counter_counts_the_eye_that_winked_when_sides_are_swapped(settings):
    calls = []
    host = SimpleNamespace(
        blink=SimpleNamespace(update=lambda *_: LEFT),
        settings=settings.model_copy(update={"swap_blink_sides": True,
                                             "right_blink_action": "go_back"}),
        mouse=SimpleNamespace(go_back=lambda: calls.append("go_back")),
        dwell=DwellClicker(), paused=False, _wink_point=None, _live=LiveState(settings))
    TrackingWorker._handle_blink(host, GazeReading(face_found=True))
    assert calls == ["go_back"]
    assert _saved(settings)["winks"] == {"left": 1, "right": 0}


def test_home_command_opens_home_suite_and_keeps_tracking(settings, monkeypatch):
    opened = []
    monkeypatch.setattr(tracking_worker.webbrowser, "open", opened.append)
    commands = queue.Queue()
    commands.put(HOME)
    quits = []
    host = SimpleNamespace(commands=commands, settings=settings, quit=lambda: quits.append(1))
    TrackingWorker._handle_commands(host)
    assert opened == [f"{settings.site_url.rstrip('/')}/home"]
    assert quits == []
