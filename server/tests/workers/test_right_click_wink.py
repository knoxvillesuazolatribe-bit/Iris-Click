"""Adviser: the right wink is a real mouse right-click; Back moves to the control bar."""

import queue
from types import SimpleNamespace

from app.config import Settings
from app.core.detection.blink_detector import RIGHT
from app.core.gaze.estimator import GazeReading
from app.desktop.system_tray import BACK
from app.services.home_service import gesture_guide
from app.workers import extra_keys, tracking_worker
from app.workers.tracking_worker import TrackingWorker
from tests.workers.test_tracking_worker import _blink_host, settings  # noqa: F401 - fixture


def test_right_click_is_the_default_right_wink():
    assert Settings.model_fields["right_blink_action"].default == "right_click"


def test_right_wink_right_clicks(settings):  # noqa: F811
    host = _blink_host(settings, RIGHT, right_blink_action="right_click")
    TrackingWorker._handle_blink(host, GazeReading(face_found=True))
    assert host.mouse.calls == ["right_click"]


def test_gesture_guide_says_right_click(settings):  # noqa: F811
    guide = gesture_guide(settings.model_copy(update={"right_blink_action": "right_click"}))
    assert any(row["action"] == "Right-click" for row in guide)


def test_back_is_alt_left():
    assert extra_keys.KEYS[BACK] == ("alt", "left")


def test_back_command_presses_alt_left(settings, monkeypatch):  # noqa: F811
    pressed = []
    monkeypatch.setattr(tracking_worker.extra_keys, "press", pressed.append)
    commands = queue.Queue()
    commands.put(BACK)
    host = SimpleNamespace(commands=commands, settings=settings, quit=lambda: None)
    TrackingWorker._handle_commands(host)
    assert pressed == [BACK]
