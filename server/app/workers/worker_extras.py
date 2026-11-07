"""Phase 6 and 9 features wired into the tracking worker through small hooks.

Built once in TrackingWorker.__init__; each worker hook calls one method here
inside contextlib.suppress, so a failure never affects clicks, Back or the cursor.
"""

import time
import tkinter as tk
from collections.abc import Callable

from app.config import Settings
from app.desktop.target_assist import tk_button_targets
from app.workers.both_blink import IGNORED, BothBlinkRouter
from app.workers.edge_scroll import EdgeScroller
from app.workers.screenshot_capture import ScreenshotTaker
from app.workers.virtual_keyboard import VirtualKeyboard
from app.workers.worker_notes import WorkerNotes


def widget_rect(widget: tk.Misc) -> tuple[int, int, int, int]:
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    return x, y, x + widget.winfo_width(), y + widget.winfo_height()


def _no_scroll_areas(control_bar: tk.Misc, keyboard: VirtualKeyboard) -> list[tuple[int, int, int, int]]:
    """Edge scroll never starts on the control bar or the open keyboard."""
    areas = [widget_rect(control_bar)]
    if keyboard.visible:
        areas.append(widget_rect(keyboard.win))
    return areas


class WorkerExtras:
    def __init__(self, root: tk.Misc, control_bar: tk.Misc, settings: Settings,
                 profile_id: str | None, screen_w: int, screen_h: int,
                 announce: Callable[[str, float], None] | None = None):
        # The callbacks below capture locals, never self: a cycle back to this object
        # would leave the Tk windows to the garbage collector, which may run on another
        # thread, and Tk aborts when it is torn down off its own thread.
        notes = WorkerNotes(
            root, control_bar, screen_w, screen_h,
            announce=(lambda text: announce(text, time.monotonic())) if announce else None)
        screenshot = ScreenshotTaker(settings, profile_id, notify=notes.post_toast)
        keyboard = VirtualKeyboard(
            root, screen_w, screen_h, anchor=control_bar,
            on_toggle=lambda shown: notes.post_toast("Keyboard open" if shown else "Keyboard closed"))
        self.notes, self.screenshot, self.keyboard = notes, screenshot, keyboard
        self.edge_scroll = EdgeScroller(settings, screen_w, screen_h,
                                        exclude=lambda: _no_scroll_areas(control_bar, keyboard),
                                        on_scroll=notes.show_scroll)
        self.both = BothBlinkRouter(
            schedule=root.after, cancel=root.after_cancel,
            on_single=lambda: screenshot.take(time.monotonic()),
            on_double=keyboard.toggle)

    def observe_closure(self, eyes_closing: bool, now: float) -> None:
        self.screenshot.observe(eyes_closing, now)

    def both_blink(self, now: float) -> str:
        """Screenshot (single) or keyboard (double); what happened, for the worker log."""
        if self.screenshot.is_resting():
            return IGNORED
        return self.both.blink(now)

    def toggle_keyboard(self) -> bool:
        return self.keyboard.toggle()

    def keyboard_targets(self) -> list:
        """The keyboard's keys for cursor snapping, while it is open."""
        if not self.keyboard.visible:
            return []
        return tk_button_targets(self.keyboard.win)

    def cursor_drawn(self, x: float, y: float, now: float) -> None:
        self.edge_scroll.update(x, y, now)
