"""Every calibration window screen draws without errors (hidden Tk window, no camera)."""

import tkinter as tk

import pytest

from app.desktop_calibration import flow as F
from app.desktop_calibration.window import CalibrationWindow


@pytest.fixture(scope="module")
def window():
    # One hidden root for all screens: creating many Tk roots in a row is flaky on Windows.
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.withdraw()
    w = CalibrationWindow(port=1)
    w.root, w.width, w.height = root, 1920, 1080
    w.canvas = tk.Canvas(root, width=1920, height=1080)
    yield w
    root.destroy()


def view(**changes):
    base = {"phase": F.CHECKING, "paused": False, "dot": None, "done": 0, "total": 13, "countdown": None,
            "advice": None, "checks": {"face": True, "eyes": False, "distance": True}, "message": None,
            "result": None, "retry_in": None}
    return {**base, **changes}


@pytest.mark.parametrize("v", [
    view(phase=F.CONNECTING),
    view(advice="Move a little closer."),
    view(phase=F.COUNTDOWN, countdown=3),
    view(phase=F.DOTS, done=7, dot={"x": 0.04, "y": 0.96, "state": "collecting"}),
    view(phase=F.DOTS, dot={"x": 0.5, "y": 0.5, "state": "accepted"}),
    view(phase=F.DOTS, dot={"x": 0.5, "y": 0.5, "state": "rest"}, message="That dot was not clear."),
    view(phase=F.DOTS, paused=True, dot={"x": 0.5, "y": 0.5, "state": "waiting"}),
    view(phase=F.FITTING, done=13),
    view(phase=F.SUCCESS, result={"status": "success", "accuracy_percent": 96.4, "low_accuracy": False}),
    view(phase=F.SUCCESS, result={"status": "success", "accuracy_percent": 91.2, "low_accuracy": True}),
    view(phase=F.FAILED, message="Not accurate enough.", retry_in=7),
    view(phase=F.FAILED, message="Not accurate enough."),
    view(phase=F.FAILED, message=F.LOST),
])
def test_screen_draws(window, v):
    window._draw(v, now=12.3)
    assert window.canvas.find_all()
