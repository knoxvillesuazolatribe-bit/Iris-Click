"""Runs the real Tk overlay and tray icon with a fake camera and a fake mouse.

The fake camera never sees a face, so nothing is clicked or moved for real.
Only one test creates a Tk root: Tcl fails to re-initialise a second
interpreter in the same process on Windows.
"""

import time
from types import SimpleNamespace

import pytest

from app.core.actions.dwell_click import DwellClicker
from app.core.detection.blink_detector import BOTH, LEFT, RIGHT
from app.core.gaze.estimator import GazeReading
from app.workers import tracking_worker
from app.workers.tracking_worker import PidFile, TrackingWorker


class NoFaceTracker:
    running = True
    last_error = None
    deep_gaze_available = False

    def read(self):
        return GazeReading(face_found=False, captured_at=time.perf_counter(), frame_id=1)


class RecordingMouse:
    def __init__(self):
        self.calls = []

    def position(self):
        return 500, 500

    def moved_by_user(self):
        return False

    def screen_size(self):
        return 1920, 1080

    def left_click(self, x=None, y=None):
        self.calls.append("left_click" if x is None else ("left_click", x, y))

    def right_click(self):
        self.calls.append("right_click")

    def go_back(self):
        self.calls.append("go_back")

    def undo(self):
        self.calls.append("undo")

    def forget_position(self):
        pass


@pytest.fixture
def settings(tmp_path):
    return tracking_worker.get_settings().model_copy(update={
        "worker_pid_path": tmp_path / "tracking_worker.pid",
        "swap_blink_sides": False,
        "right_blink_action": "go_back",
        "target_snap_enabled": False,
    })


class SilentSpeaker:
    def __init__(self):
        self.lines = []

    def start(self):
        pass

    def stop(self):
        pass

    def say(self, text):
        self.lines.append(text)


def test_worker_runs_and_quits_on_stop_request(settings, monkeypatch):
    monkeypatch.setattr(tracking_worker, "MouseController", RecordingMouse)
    monkeypatch.setattr(tracking_worker, "Speaker", SilentSpeaker)
    pid_file = PidFile(settings)
    assert pid_file.claim("test-profile")
    worker = TrackingWorker(settings, NoFaceTracker(), model=None, pid_file=pid_file)
    worker.root.after(1200, lambda: pid_file.stop_path.write_text("stop"))
    started = time.monotonic()

    worker.run()
    pid_file.release()

    assert time.monotonic() - started < 5
    assert worker.tray._status.startswith("IrisClick: Face not visible")
    assert worker.bar._last_state[:2] == (tracking_worker.REASON_TEXT["no_face"], "problem")
    assert worker.speaker.lines == ["Eye tracking is on."]
    assert worker.mouse.calls == []
    assert not settings.worker_pid_path.exists()


def test_unclear_eyes_at_a_bad_distance_asks_to_move_forward():
    key, text = TrackingWorker._problem_speech("invalid_features", None, "closer")
    assert key == "closer"
    assert "move forward" in text


def test_unclear_eyes_speech():
    key, text = TrackingWorker._problem_speech("missing_features", None, None)
    assert "cannot be clearly detected" in text
    assert "move forward" in text


def _blink_host(settings, side, paused=False, wink_point=None, **overrides):
    return SimpleNamespace(
        blink=SimpleNamespace(update=lambda *_: side),
        settings=settings.model_copy(update=overrides),
        mouse=RecordingMouse(),
        dwell=DwellClicker(),
        paused=paused,
        _wink_point=wink_point,
    )


@pytest.mark.parametrize(("side", "expected"), [(LEFT, "left_click"), (RIGHT, "go_back")])
def test_winks_map_to_commands(settings, side, expected):
    host = _blink_host(settings, side)
    TrackingWorker._handle_blink(host, GazeReading(face_found=True))
    assert host.mouse.calls == [expected]


def test_right_wink_can_undo(settings):
    host = _blink_host(settings, RIGHT, right_blink_action="undo")
    TrackingWorker._handle_blink(host, GazeReading(face_found=True))
    assert host.mouse.calls == ["undo"]


def test_swap_blink_sides(settings):
    host = _blink_host(settings, LEFT, swap_blink_sides=True)
    TrackingWorker._handle_blink(host, GazeReading(face_found=True))
    assert host.mouse.calls == ["go_back"]


def test_winks_ignored_while_paused(settings):
    host = _blink_host(settings, LEFT, paused=True)
    TrackingWorker._handle_blink(host, GazeReading(face_found=True))
    assert host.mouse.calls == []


def test_both_eye_blink_triggers_nothing(settings):
    host = _blink_host(settings, BOTH)
    TrackingWorker._handle_blink(host, GazeReading(face_found=True))
    assert host.mouse.calls == []


class HandOffMouse:
    def __init__(self):
        self.pos = (500, 500)
        self.user_moved = False

    def position(self):
        return self.pos

    def moved_by_user(self):
        return self.user_moved


def _handoff_host(settings):
    host = SimpleNamespace(settings=settings, mouse=HandOffMouse(), resets=0,
                           _handoff_until=0.0, _handoff_pos=None)
    host._reset_motion = lambda: setattr(host, "resets", host.resets + 1)
    return host


def test_physical_mouse_hands_off_and_gaze_resumes_after_it_stops(settings):
    host = _handoff_host(settings)
    assert TrackingWorker._mouse_in_use(host, 0.0) is False

    host.mouse.user_moved = True
    assert TrackingWorker._mouse_in_use(host, 1.0) is True
    host.mouse.user_moved = False
    host.mouse.pos = (1919, 0)  # e.g. pushed to the corner to close a window
    assert TrackingWorker._mouse_in_use(host, 2.0) is True
    # Still inside the hand-off window after the last movement.
    assert TrackingWorker._mouse_in_use(host, 2.0 + settings.mouse_handoff_s - 0.1) is True
    assert TrackingWorker._mouse_in_use(host, 2.0 + settings.mouse_handoff_s + 0.1) is False
    assert host.resets == 2


def test_left_wink_clicks_where_the_user_looked_before_the_lid_dropped(settings):
    host = _blink_host(settings, LEFT, wink_point=(1890.0, 20.0))
    TrackingWorker._handle_blink(host, GazeReading(face_found=True))
    assert host.mouse.calls == [("left_click", 1890.0, 20.0)]
