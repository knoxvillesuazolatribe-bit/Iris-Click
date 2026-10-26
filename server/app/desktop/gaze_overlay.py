"""Always-on-top, click-through gaze cursor drawn at the eyes' pointer.

The OS cursor is moved separately; this ring shows where the eyes are
pointing and how far a dwell click has progressed. It never receives mouse
input, keyboard focus or a taskbar button.
"""

import tkinter as tk

from app.desktop.display import make_tool_window

BACKGROUND = "#0F1B2D"
HIGHLIGHT = "#FFD23F"
# Tk's -transparentcolor key; must never be used by anything drawn.
TRANSPARENT = "#010203"
GAZE_WIDTH = 4
RING_RADIUS = 30
# Sharp "V" pyramid pointing up; its tip is the exact gaze point.
PYRAMID_HALF_WIDTH = 11
PYRAMID_HEIGHT = 30


class GazeOverlay:
    def __init__(self, root: tk.Tk, screen_w: int, screen_h: int):
        self.root = root
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.geometry(f"{screen_w}x{screen_h}+0+0")
        root.configure(bg=TRANSPARENT)
        root.attributes("-transparentcolor", TRANSPARENT)
        self.canvas = tk.Canvas(root, bg=TRANSPARENT, highlightthickness=0,
                                width=screen_w, height=screen_h)
        self.canvas.pack(fill="both", expand=True)
        make_tool_window(root, click_through=True)

    def keep_on_top(self):
        self.root.attributes("-topmost", True)

    def hide_cursor(self):
        self.canvas.delete("cursor")

    def show_cursor(self, x: float, y: float, dwell_progress: float, target=None):
        """``target``: the snapped control's rect (left, top, right, bottom), outlined."""
        self.canvas.delete("cursor")
        if target is not None:
            left, top, right, bottom = target
            for colour, width in ((BACKGROUND, GAZE_WIDTH + 4), (HIGHLIGHT, GAZE_WIDTH)):
                self.canvas.create_rectangle(left - 3, top - 3, right + 3, bottom + 3,
                                             outline=colour, width=width, tags="cursor")
        # Dark outline under the bright pyramid keeps it visible on any content.
        pyramid = (x, y,
                   x - PYRAMID_HALF_WIDTH, y + PYRAMID_HEIGHT,
                   x, y + PYRAMID_HEIGHT * 0.72,
                   x + PYRAMID_HALF_WIDTH, y + PYRAMID_HEIGHT)
        self.canvas.create_polygon(*pyramid, fill=HIGHLIGHT, outline=BACKGROUND,
                                   width=3, joinstyle="miter", tags="cursor")
        if dwell_progress > 0:
            extent = -360 * dwell_progress
            for colour, width in ((BACKGROUND, GAZE_WIDTH + 4), (HIGHLIGHT, GAZE_WIDTH)):
                self.canvas.create_arc(x - RING_RADIUS, y - RING_RADIUS,
                                       x + RING_RADIUS, y + RING_RADIUS,
                                       start=90, extent=extent, style="arc",
                                       outline=colour, width=width, tags="cursor")
