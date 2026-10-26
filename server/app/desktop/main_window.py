"""Floating, always-on-top control bar for the tracking worker.

Large buttons so they can be hit by looking at them and winking. The window is
non-activating, so pressing a button never takes keyboard focus from the app
the user is working in. Drag it by the IrisClick label.
"""

import queue
import tkinter as tk

from app.desktop.display import make_tool_window
from app.desktop.system_tray import PAUSE, QUIT, RECALIBRATE, TOGGLE_VOICE

BACKGROUND = "#0F1B2D"
PANEL = "#1B2B45"
TEXT = "#FFFFFF"
SECONDARY = "#C9D6E8"
PRIMARY = "#4DA3FF"
SUCCESS = "#3DDC84"
WARNING = "#FFB020"
ERROR = "#FF6B6B"
STATUS_COLOURS = {"tracking": SUCCESS, "paused": WARNING, "problem": ERROR}

FONT = ("Segoe UI", 12, "bold")
TOP_MARGIN_PX = 8
STATUS_CHARS = 34
STATUS_WRAP_PX = 300
# A stray wink can land on Quit by accident; require a second press in time.
QUIT_CONFIRM_MS = 4000


class ControlBar:
    def __init__(self, root: tk.Misc, commands: "queue.Queue[str]", screen_w: int):
        self._commands = commands
        self._quit_armed_job = None
        self._last_state = None
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=PRIMARY)

        frame = tk.Frame(self.win, bg=BACKGROUND, padx=8, pady=6)
        frame.pack(padx=2, pady=2)

        handle = tk.Label(frame, text="👁 IrisClick", font=FONT, bg=BACKGROUND, fg=TEXT,
                          cursor="fleur", padx=6)
        handle.pack(side="left")
        self._dot = tk.Label(frame, text="●", font=("Segoe UI", 16), bg=BACKGROUND, fg=SECONDARY)
        self._dot.pack(side="left", padx=(6, 2))
        self._status = tk.Label(frame, text="starting", font=("Segoe UI", 11), bg=BACKGROUND,
                                fg=SECONDARY, width=STATUS_CHARS, anchor="w",
                                justify="left", wraplength=STATUS_WRAP_PX)
        self._status.pack(side="left", padx=(0, 8))

        self._pause = self._button(frame, "Pause", PAUSE)
        self._voice = self._button(frame, "Voice: on", TOGGLE_VOICE)
        self._button(frame, "Recalibrate", RECALIBRATE)
        self._quit = self._button(frame, "Quit", None, command=self._quit_pressed)

        for widget in (handle, self._dot, self._status):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)

        self.win.update_idletasks()
        x = max(0, (screen_w - self.win.winfo_reqwidth()) // 2)
        self.win.geometry(f"+{x}+{TOP_MARGIN_PX}")
        make_tool_window(self.win)

    def _button(self, parent, text, command_name, command=None):
        button = tk.Button(
            parent, text=text, font=FONT, bg=PANEL, fg=TEXT, activebackground=PRIMARY,
            activeforeground=BACKGROUND, relief="flat", padx=14, pady=8, bd=0,
            highlightthickness=0, cursor="hand2",
            command=command or (lambda: self._commands.put(command_name)),
        )
        button.pack(side="left", padx=3)
        return button

    def _quit_pressed(self):
        if self._quit_armed_job is not None:
            self._commands.put(QUIT)
            return
        self._quit.configure(text="Press again to quit", bg=ERROR, fg=BACKGROUND)
        self._quit_armed_job = self.win.after(QUIT_CONFIRM_MS, self._disarm_quit)

    def _disarm_quit(self):
        self._quit_armed_job = None
        self._quit.configure(text="Quit", bg=PANEL, fg=TEXT)

    def _start_drag(self, event):
        self._drag_offset = (event.x_root - self.win.winfo_x(), event.y_root - self.win.winfo_y())

    def _drag(self, event):
        dx, dy = self._drag_offset
        self.win.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def keep_on_top(self):
        self.win.attributes("-topmost", True)
        self.win.lift()

    def set_state(self, status: str, kind: str, paused: bool, voice_enabled: bool):
        """kind: "tracking", "paused" or "problem"."""
        state = (status, kind, paused, voice_enabled)
        if state == self._last_state:
            return
        self._last_state = state
        self._voice.configure(text=f"Voice: {'on' if voice_enabled else 'off'}")
        self._status.configure(text=status)
        self._dot.configure(fg=STATUS_COLOURS[kind])
        self._pause.configure(text="Resume" if paused else "Pause",
                              bg=SUCCESS if paused else PANEL,
                              fg=BACKGROUND if paused else TEXT)
