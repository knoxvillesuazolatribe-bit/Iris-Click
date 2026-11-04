"""Phase 6 features wired into the tracking worker through small hooks.

Built once in TrackingWorker.__init__; each worker hook calls one method here
inside contextlib.suppress, so a failure never affects clicks, Back or the cursor.
"""

import time
import tkinter as tk
from collections.abc import Callable

from app.config import Settings
from app.workers.edge_scroll import EdgeScroller
from app.workers.screenshot_capture import ScreenshotTaker
from app.workers.worker_notes import WorkerNotes


def widget_rect(widget: tk.Misc) -> tuple[int, int, int, int]:
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    return x, y, x + widget.winfo_width(), y + widget.winfo_height()


class WorkerExtras:
    def __init__(self, root: tk.Misc, control_bar: tk.Misc, settings: Settings,
                 profile_id: str | None, screen_w: int, screen_h: int,
                 announce: Callable[[str, float], None] | None = None):
        self.notes = WorkerNotes(
            root, control_bar, screen_w, screen_h,
            announce=(lambda text: announce(text, time.monotonic())) if announce else None)
        self.screenshot = ScreenshotTaker(settings, profile_id, notify=self.notes.post_toast)
        self.edge_scroll = EdgeScroller(settings, screen_w, screen_h,
                                        exclude=lambda: [widget_rect(control_bar)],
                                        on_scroll=self.notes.show_scroll)

    def observe_closure(self, eyes_closing: bool, now: float) -> None:
        self.screenshot.observe(eyes_closing, now)

    def both_blink(self, now: float) -> bool:
        return self.screenshot.on_both_blink(now)

    def cursor_drawn(self, x: float, y: float, now: float) -> None:
        self.edge_scroll.update(x, y, now)
