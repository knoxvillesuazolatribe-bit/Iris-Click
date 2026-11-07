"""Control bar layout on wide and narrow screens (H3 buttons wrap only when needed).

Runs in a child process: Tcl cannot start a second interpreter in the
pytest process on Windows (test_tracking_worker.py already owns one).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[2]

SCRIPT = r"""
import json, queue, sys, tkinter as tk
sys.path.insert(0, ".")
from app.desktop.main_window import ControlBar

root = tk.Tk()
root.withdraw()
result = {}
for screen_w in (1920, 1366):
    bar = ControlBar(root, queue.Queue(), screen_w)
    bar.win.update_idletasks()
    first_row = bar._quit.master
    labels = lambda parent: [w.cget("text") for w in parent.pack_slaves() if isinstance(w, tk.Button)]
    result[screen_w] = {
        "width": bar.win.winfo_reqwidth(),
        "height": bar.win.winfo_reqheight(),
        "row1": labels(first_row),
        "row1_has_extras": bar._extra_row in first_row.pack_slaves(),
        "extras": labels(bar._extra_row),
        "extra_height": bar._extra_row.winfo_reqheight(),
        "button_height": bar._quit.winfo_reqheight(),
    }
    bar.win.destroy()
root.destroy()
print(json.dumps(result))
"""

ORIGINAL = ["Pause", "Voice: on", "Camera: on", "Edge: medium", "Re-centre", "Recalibrate"]
ADDED = ["Home", "Forward", "Next Tab", "Keyboard"]


@pytest.fixture(scope="module")
def layout():
    done = subprocess.run([sys.executable, "-c", SCRIPT], cwd=SERVER_DIR, capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return {int(k): v for k, v in json.loads(done.stdout.strip().splitlines()[-1]).items()}


def test_wide_screen_keeps_one_row(layout):
    wide = layout[1920]
    assert wide["row1_has_extras"] is True
    assert wide["extras"] == ADDED
    assert wide["width"] <= 1920
    # The group adds no padding: the row is no taller than its buttons need.
    assert wide["extra_height"] == wide["button_height"]


def test_narrow_screen_moves_added_buttons_to_a_second_row(layout):
    narrow, wide = layout[1366], layout[1920]
    assert narrow["row1_has_extras"] is False
    assert narrow["extras"] == ADDED
    assert narrow["width"] <= 1366
    assert narrow["height"] > wide["height"]


@pytest.mark.parametrize("screen_w", [1920, 1366])
def test_original_buttons_keep_their_order_and_quit_stays_last(layout, screen_w):
    row1 = layout[screen_w]["row1"]
    assert row1[:len(ORIGINAL)] == ORIGINAL
    assert row1[-1] == "Quit"
