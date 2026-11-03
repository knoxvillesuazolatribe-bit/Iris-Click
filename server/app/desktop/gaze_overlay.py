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
LINK = "#4DA3FF"
LINK_WIDTH = 2
LINK_DASH = (8, 6)
TRAIL = "#3DDC84"
RAW = "#FF6B6B"
RAW_RADIUS = 6
DOT_RADIUS = 26
DOT_CORE = 7
SECONDARY_RING = "#C9D6E8"
FINE_RING = "#3DDC84"
FINE_RING_RADIUS = 14


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
        self.canvas.delete("cursor", "link")

    def show_link(self, eye, cursor, trail=(), raw=None):
        """Navigation visualisation under the cursor: a line from the eyes in the
        camera preview to the cursor, the recent cursor path, and the raw
        (unfiltered) gaze point. ``eye``/``raw`` may be None."""
        self.canvas.delete("link")
        if len(trail) >= 2:
            points = [v for point in trail for v in point]
            self.canvas.create_line(*points, fill=TRAIL, width=2, smooth=True, tags="link")
        if eye is not None:
            for colour, width in ((BACKGROUND, LINK_WIDTH + 3), (LINK, LINK_WIDTH)):
                self.canvas.create_line(*eye, *cursor, fill=colour, width=width,
                                        dash=LINK_DASH, tags="link")
        if raw is not None:
            x, y = raw
            self.canvas.create_oval(x - RAW_RADIUS, y - RAW_RADIUS, x + RAW_RADIUS,
                                    y + RAW_RADIUS, outline=RAW, width=2, tags="link")
        self.canvas.tag_raise("cursor")

    def hide_link(self):
        self.canvas.delete("link")

    def show_dot(self, x: float, y: float, progress: float, label: str = ""):
        """A re-centre dot; its ring fills while samples are collected."""
        self.canvas.delete("dot")
        r = DOT_RADIUS
        self.canvas.create_oval(x - r, y - r, x + r, y + r, outline=BACKGROUND,
                                width=GAZE_WIDTH + 4, tags="dot")
        self.canvas.create_oval(x - r, y - r, x + r, y + r, outline=SECONDARY_RING,
                                width=GAZE_WIDTH, tags="dot")
        if progress > 0:
            self.canvas.create_arc(x - r, y - r, x + r, y + r, start=90,
                                   extent=-359.9 * progress, style="arc", outline=HIGHLIGHT,
                                   width=GAZE_WIDTH, tags="dot")
        self.canvas.create_oval(x - DOT_CORE, y - DOT_CORE, x + DOT_CORE, y + DOT_CORE,
                                fill=HIGHLIGHT, outline=BACKGROUND, width=2, tags="dot")
        if label:
            # Below the dot, or above it near the bottom edge.
            ty = y + r + 22 if y + r + 40 < self.canvas.winfo_height() else y - r - 22
            self.canvas.create_text(x, ty, text=label, fill=HIGHLIGHT,
                                    font=("Segoe UI", 14, "bold"), tags="dot")

    def hide_dot(self):
        self.canvas.delete("dot")

    def show_cursor(self, x: float, y: float, dwell_progress: float, target=None,
                    fine: bool = False):
        """``target``: the snapped control's rect (left, top, right, bottom), outlined.
        ``fine``: head fine-aim is active; a small ring marks the exact point."""
        self.canvas.delete("cursor")
        if fine:
            r = FINE_RING_RADIUS
            for colour, width in ((BACKGROUND, 5), (FINE_RING, 2)):
                self.canvas.create_oval(x - r, y - r, x + r, y + r, outline=colour,
                                        width=width, tags="cursor")
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
