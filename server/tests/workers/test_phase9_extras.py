"""Phase 9 worker additions: single vs double both-eye blink, on-screen keyboard."""

import json
import queue
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.actions.dwell_click import DwellClicker
from app.core.detection.blink_detector import BOTH
from app.core.gaze.estimator import GazeReading
from app.desktop.system_tray import KEYBOARD
from app.workers.both_blink import DOUBLE, DOUBLE_WINDOW_S, PENDING, BothBlinkRouter
from app.workers.screenshot_capture import MAX_CLOSURE_S
from app.workers.tracking_worker import TrackingWorker
from app.workers.virtual_keyboard import GAP_PX, KEY_PX, ROWS, key_action, keyboard_size
from app.workers.worker_extras import WorkerExtras

SERVER_DIR = Path(__file__).resolve().parents[2]


class FakeScheduler:
    def __init__(self):
        self.jobs: dict[int, tuple[int, object]] = {}
        self.cancelled: list[int] = []
        self._next = 0

    def after(self, ms, fn):
        self._next += 1
        self.jobs[self._next] = (ms, fn)
        return self._next

    def cancel(self, job):
        self.cancelled.append(job)
        self.jobs.pop(job, None)

    def run_all(self):
        jobs, self.jobs = self.jobs, {}
        for _ms, fn in jobs.values():
            fn()


@pytest.fixture
def router():
    sched = FakeScheduler()
    events = []
    r = BothBlinkRouter(sched.after, sched.cancel, on_single=lambda: events.append("screenshot"),
                        on_double=lambda: events.append("keyboard"))
    r.sched, r.events = sched, events
    return r


# --- Single vs double both-eye blink --------------------------------------------------------

def test_single_blink_waits_then_takes_a_screenshot(router):
    assert router.blink(10.0) == PENDING
    assert router.events == [] and router.waiting
    [(ms, _fn)] = router.sched.jobs.values()
    assert ms == int(DOUBLE_WINDOW_S * 1000)
    router.sched.run_all()
    assert router.events == ["screenshot"] and not router.waiting


def test_double_blink_toggles_the_keyboard_without_a_screenshot(router):
    router.blink(10.0)
    assert router.blink(10.0 + 1.1) == DOUBLE
    assert router.events == ["keyboard"]
    assert router.sched.jobs == {} and router.sched.cancelled == [1]
    router.sched.run_all()
    assert router.events == ["keyboard"]


def test_a_late_second_blink_counts_as_a_new_first_blink(router):
    router.blink(10.0)
    assert router.blink(10.0 + DOUBLE_WINDOW_S + 0.2) == PENDING
    assert router.events == []  # the first one's screenshot was replaced, not doubled
    router.sched.run_all()
    assert router.events == ["screenshot"]


def test_three_blinks_toggle_once_then_wait_again(router):
    router.blink(10.0)
    router.blink(11.0)
    assert router.blink(12.0) == PENDING
    assert router.events == ["keyboard"]


def _extras(resting: bool):
    """WorkerExtras without Tk windows: only what both_blink uses."""
    extras = object.__new__(WorkerExtras)
    extras.screenshot = SimpleNamespace(is_resting=lambda: resting)
    sched = FakeScheduler()
    extras.both = BothBlinkRouter(sched.after, sched.cancel, lambda: None, lambda: None)
    return extras


def test_resting_eyes_are_ignored():
    assert _extras(resting=True).both_blink(10.0) == "ignored"
    assert _extras(resting=False).both_blink(10.0) == PENDING
    assert MAX_CLOSURE_S == 1.5


# --- Keyboard keys ------------------------------------------------------------------------------

@pytest.mark.parametrize(("key", "caps", "expected"), [
    ("Q", False, ("write", ("q",))), ("Q", True, ("write", ("Q",))),
    ("?", False, ("write", ("?",))), ("'", True, ("write", ("'",))),
    ("backspace", False, ("press", ("backspace",))), ("enter", False, ("press", ("enter",))),
    ("space", False, ("press", ("space",))),
    ("copy", False, ("hotkey", ("ctrl", "c"))), ("paste", False, ("hotkey", ("ctrl", "v"))),
    ("caps", False, ("caps", ())), ("move", False, ("move", ())), ("close", False, ("close", ())),
])
def test_key_actions(key, caps, expected):
    assert key_action(key, caps) == expected


def test_layout_has_every_letter_and_12_columns_per_row():
    keys = [k for row in ROWS for _label, k, _span in row]
    assert set("ABCDEFGHIJKLMNOPQRSTUVWXYZ") <= set(keys)
    assert {"backspace", "enter", "space", "copy", "paste", "caps", "close", "move"} <= set(keys)
    assert all(sum(span for *_rest, span in row) == 12 for row in ROWS)
    assert keyboard_size()[:2] == (12 * KEY_PX + 11 * GAP_PX, 4 * KEY_PX + 3 * GAP_PX)


# --- Hooks in tracking_worker.py ------------------------------------------------------------------

def test_both_eye_blink_hook_routes_through_extras():
    calls = []
    host = SimpleNamespace(
        blink=SimpleNamespace(update=lambda *_: BOTH),
        settings=SimpleNamespace(swap_blink_sides=False, blink_click_enabled=True,
                                 right_blink_action="go_back"),
        mouse=SimpleNamespace(), dwell=DwellClicker(), paused=False, _wink_point=None,
        _extras=SimpleNamespace(both_blink=lambda now: calls.append(now) or PENDING))
    TrackingWorker._handle_blink(host, GazeReading(face_found=True))
    assert len(calls) == 1


def test_keyboard_command_toggles_the_keyboard():
    toggles = []
    commands = queue.Queue()
    commands.put(KEYBOARD)
    host = SimpleNamespace(commands=commands, quit=lambda: toggles.append("quit"),
                           _extras=SimpleNamespace(toggle_keyboard=lambda: toggles.append("kb")))
    TrackingWorker._handle_commands(host)
    assert toggles == ["kb"]


def test_keyboard_command_without_extras_is_harmless():
    commands = queue.Queue()
    commands.put(KEYBOARD)
    TrackingWorker._handle_commands(SimpleNamespace(commands=commands, _extras=None))


# --- The real keyboard window (child process: one Tcl interpreter per process) ----------------

WINDOW_SCRIPT = r"""
import json, sys, tkinter as tk
sys.path.insert(0, ".")
from app.workers.virtual_keyboard import VirtualKeyboard
root = tk.Tk(); root.withdraw()
sent, toggles = [], []
kb = VirtualKeyboard(root, 1366, 768, send=lambda kind, args: sent.append([kind, list(args)]),
                     on_toggle=toggles.append)
kb.show(); root.update()
b = {k: (w.winfo_x(), w.winfo_y(), w.winfo_width(), w.winfo_height()) for k, w in kb.buttons.items()}
win_w, win_h = kb.win.winfo_width(), kb.win.winfo_height()
bottom_y = kb.win.winfo_y()
for key in ("H", "caps", "I", "space", "copy", "move"): kb.press(key)
root.update(); top_y = kb.win.winfo_y()
kb.press("close"); root.update()
print(json.dumps({"buttons": b, "win": [win_w, win_h], "sent": sent, "toggles": toggles,
                  "bottom_y": bottom_y, "top_y": top_y, "visible": kb.visible,
                  "caps": kb.caps}))
root.destroy()
"""


@pytest.fixture(scope="module")
def window():
    done = subprocess.run([sys.executable, "-c", WINDOW_SCRIPT], cwd=SERVER_DIR,
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_keys_are_80px_with_24px_gaps(window):
    b = window["buttons"]
    assert all(h == KEY_PX for *_xyw, h in b.values())
    assert b["Q"][2] == KEY_PX and b["backspace"][2] == 2 * KEY_PX + GAP_PX
    assert b["W"][0] - (b["Q"][0] + b["Q"][2]) == GAP_PX
    assert b["A"][1] - (b["Q"][1] + b["Q"][3]) == GAP_PX
    assert window["win"][0] <= 1366  # fits a 1366 px screen


def test_window_types_moves_and_closes(window):
    assert window["sent"] == [["write", ["h"]], ["write", ["I"]], ["press", ["space"]],
                              ["hotkey", ["ctrl", "c"]]]
    assert window["top_y"] < window["bottom_y"]
    assert window["visible"] is False and window["toggles"] == [True, False]
    assert window["caps"] is True
