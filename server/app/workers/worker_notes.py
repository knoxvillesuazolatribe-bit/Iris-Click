"""Small on-screen notes for the tracking worker: "Screenshot saved", "Scrolling down".

Click-through and never focused, so they cannot get in the way of a gaze
click. post() is safe from any thread; everything else runs on the Tk thread.
"""

import queue
import tkinter as tk
from collections.abc import Callable

from app.desktop.display import make_tool_window

BACKGROUND = "#0F1B2D"
TEXT = "#FFFFFF"
BORDER = "#4DA3FF"
FONT = ("Segoe UI", 16, "bold")
POLL_MS = 100
TOAST_MS = 2000
GAP_PX = 12


class Note:
    """One click-through label window that can be shown, moved and hidden."""

    def __init__(self, root: tk.Misc):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=BORDER)
        self.label = tk.Label(self.win, font=FONT, bg=BACKGROUND, fg=TEXT, padx=18, pady=10)
        self.label.pack(padx=2, pady=2)
        self.win.withdraw()
        make_tool_window(self.win, click_through=True)
        self._hide_job = None

    def show(self, text: str, center_x: int, y: int, duration_ms: int | None = None,
             below: bool = True):
        """Shows ``text`` centred on ``center_x``; ``y`` is its top (or bottom if not below)."""
        self.label.configure(text=text)
        self.win.update_idletasks()
        width, height = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        top = y if below else y - height
        self.win.geometry(f"+{max(0, center_x - width // 2)}+{max(0, top)}")
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        if self._hide_job is not None:
            self.win.after_cancel(self._hide_job)
            self._hide_job = None
        if duration_ms:
            self._hide_job = self.win.after(duration_ms, self.hide)

    def hide(self):
        self._hide_job = None
        self.win.withdraw()


class WorkerNotes:
    def __init__(self, root: tk.Misc, anchor: tk.Misc, screen_w: int, screen_h: int,
                 announce: Callable[[str], None] | None = None):
        self._root = root
        self._anchor = anchor
        self._screen_w, self._screen_h = screen_w, screen_h
        self._announce = announce
        self._toast = Note(root)
        self._scroll = Note(root)
        self._queue: queue.Queue[str] = queue.Queue()
        root.after(POLL_MS, self._poll)

    def post_toast(self, text: str) -> None:
        """Thread-safe: shows ``text`` under the control bar for two seconds."""
        self._queue.put(text)

    def show_scroll(self, direction: str, band_px: int, duration_ms: int) -> None:
        """Tk thread: a banner just inside the band being scrolled."""
        if direction == "up":
            self._scroll.show("▲ Scrolling up", self._screen_w // 2, band_px + GAP_PX, duration_ms)
        else:
            self._scroll.show("▼ Scrolling down", self._screen_w // 2,
                              self._screen_h - band_px - GAP_PX, duration_ms, below=False)

    def _poll(self):
        try:
            while True:
                text = self._queue.get_nowait()
                bottom = self._anchor.winfo_rooty() + self._anchor.winfo_height()
                self._toast.show(text, self._screen_w // 2, bottom + GAP_PX, TOAST_MS)
                if self._announce is not None:
                    self._announce(text)
        except queue.Empty:
            pass
        except Exception:  # noqa: BLE001 - a note must never stop the worker
            pass
        self._root.after(POLL_MS, self._poll)
