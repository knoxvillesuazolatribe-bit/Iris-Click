"""The full-screen IrisClick Desktop calibration window (Tkinter).

Covers the whole primary screen, taskbar included, always on top, in physical pixels
(the same space the cursor uses: display.enable_dpi_awareness). All steps and timing
come from flow.CalibrationFlow; this module only draws, speaks and passes messages.
"""

import ctypes
import logging
import sys
import time
import tkinter as tk
from datetime import datetime

from app.desktop_calibration import flow as F
from app.desktop_calibration.client import Channel, urls

logger = logging.getLogger("irisclick.desktop_calibration.window")

BACKGROUND = "#0F1B2D"
PANEL = "#1B2B45"
TEXT = "#FFFFFF"
SECONDARY = "#C9D6E8"
YELLOW = "#FFD23F"
GREEN = "#3DDC84"
RED = "#FF6B6B"
GREY = "#8A96A8"
FONT = "Segoe UI"
DOT_RADIUS = 26
RING_RADIUS = 48
LOOP_MS = 30
MAX_AUTO_RETRIES = 2
VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002


def profile_name(now: datetime | None = None) -> str:
    return f"Desktop {(now or datetime.now()):%Y-%m-%d %H:%M}"


def _set_foreground(hwnd) -> None:
    """Windows only lets the foreground app hand focus over; a tap of Alt lifts that lock."""
    if sys.platform != "win32" or not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.SetForegroundWindow(hwnd)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    except (AttributeError, OSError):
        pass


class CalibrationWindow:
    def __init__(self, port: int, reason: str = "tray", speaker=None):
        self.port = port
        self.reason = reason
        self.speaker = speaker
        self.retries = 0
        self.flow: F.CalibrationFlow | None = None
        self.calibration: Channel | None = None
        self.agent: Channel | None = None
        self.previous_window = None
        self.root: tk.Tk | None = None

    # ---- life cycle
    def run(self) -> None:
        from app.desktop import display
        display.enable_dpi_awareness()
        if sys.platform == "win32":
            self.previous_window = display.foreground_window()
        root = self.root = tk.Tk()
        root.title("IrisClick calibration")
        root.configure(bg=BACKGROUND, cursor="none")
        root.overrideredirect(True)
        self.width, self.height = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{self.width}x{self.height}+0+0")
        root.attributes("-topmost", True)
        self.canvas = tk.Canvas(root, width=self.width, height=self.height, bg=BACKGROUND,
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        for key, name in (("<Return>", "enter"), ("<KP_Enter>", "enter"), ("<space>", "space"),
                          ("<Escape>", "escape")):
            root.bind(key, lambda _e, n=name: self._key(n))
        root.update_idletasks()
        if sys.platform == "win32":
            _set_foreground(display.toplevel_hwnd(root))
        root.focus_force()
        if self.speaker is None:
            from app.desktop.voice import Speaker
            self.speaker = Speaker()
            self.speaker.start()
        calibration_url, agent_url = urls(self.port)
        self.agent = Channel(agent_url)
        try:
            self.agent.open()
        except Exception as exc:  # noqa: BLE001 - the window still works, the website just is not told
            logger.warning("Agent channel unavailable: %s", exc)
            self.agent = None
        self._calibration_url = calibration_url
        self._new_attempt()
        self._last_lift = time.monotonic()
        root.after(LOOP_MS, self._loop)
        root.mainloop()

    def _new_attempt(self) -> None:
        now = time.monotonic()
        if self.calibration is not None:
            self.calibration.close()
        self.flow = F.CalibrationFlow(profile_name(), (self.width, self.height), now,
                                      auto_retry=self.retries < MAX_AUTO_RETRIES)
        self.calibration = Channel(self._calibration_url)
        try:
            self.calibration.open()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Calibration socket unavailable: %s", exc)
            self.flow.connection_lost(now)
            return
        self.flow.connected(now)

    def _finish(self) -> None:
        for channel in (self.calibration, self.agent):
            if channel is not None:
                channel.close()
        if self.speaker is not None:
            self.speaker.stop()
        root, self.root = self.root, None
        if root is not None:
            root.destroy()
        _set_foreground(self.previous_window)

    # ---- one tick
    def _key(self, name: str) -> None:
        if self.flow is not None:
            self.flow.key(name, time.monotonic())

    def _loop(self) -> None:
        if self.root is None:
            return
        now = time.monotonic()
        flow = self.flow
        for message in self.calibration.drain() if self.calibration else []:
            if message is None:
                flow.connection_lost(now)
            else:
                flow.on_message(message, now)
        for message in self.agent.drain() if self.agent else []:
            if message and message.get("type") == "calibration.cancel":
                flow.cancel(now, reason="website")
        flow.tick(now)
        for message in flow.take_outgoing():
            self.calibration.send(message)
        for message in flow.take_events():
            if self.agent is not None:
                self.agent.send(message)
        for line in flow.take_speech():
            self.speaker.say(line)
        if flow.close:
            self._finish()
            return
        if flow.restart:
            self.retries += 1
            self._new_attempt()
        if now - self._last_lift > 1.0:  # stay above anything that pops up
            self._last_lift = now
            self.root.attributes("-topmost", True)
            self.root.lift()
        self._draw(self.flow.view(now), now)
        self.root.after(LOOP_MS, self._loop)

    # ---- drawing
    def _text(self, x, y, text, size, color=TEXT, weight="bold", anchor="center", width=None):
        self.canvas.create_text(x, y, text=text, fill=color, font=(FONT, size, weight),
                                anchor=anchor, width=width or self.width * 0.8, justify="center")

    def _draw(self, view: dict, now: float) -> None:
        c, w, h = self.canvas, self.width, self.height
        c.delete("all")
        scale = max(0.6, min(w / 1920, h / 1080) * 1.0)
        big, mid, small = int(44 * scale), int(28 * scale), int(18 * scale)
        phase = view["phase"]
        if phase == F.CONNECTING:
            self._text(w / 2, h / 2, "Starting the camera…", mid)
        elif phase == F.CHECKING:
            self._text(w / 2, h * 0.22, "IrisClick – Eye calibration", big)
            self._text(w / 2, h * 0.32, "Sit comfortably and look at the centre of the screen.", mid,
                       SECONDARY, "normal")
            checks = view["checks"]
            labels = (("Face found", checks["face"]), ("Eyes clear", checks["eyes"]),
                      ("Distance OK", checks["distance"]))
            for i, (label, ok) in enumerate(labels):
                x = w / 2 + (i - 1) * w * 0.22
                c.create_oval(x - 14 * scale - w * 0.07, h * 0.47 - 14 * scale,
                              x + 14 * scale - w * 0.07, h * 0.47 + 14 * scale,
                              fill=GREEN if ok else GREY, outline="")
                self._text(x + 10 * scale, h * 0.47, label, mid, TEXT if ok else GREY)
            self._text(w / 2, h * 0.62, "Starts by itself when your eyes are steady…", mid, YELLOW)
            self._text(w / 2, h * 0.9, "Helper keys:  Enter = start now  ·  Space = pause  ·  Esc = cancel",
                       small, GREY, "normal")
        elif phase == F.COUNTDOWN:
            self._text(w / 2, h * 0.45, str(view["countdown"] or ""), int(200 * scale), YELLOW)
            self._text(w / 2, h * 0.68, "Only move your eyes.", mid, SECONDARY, "normal")
        elif phase in (F.DOTS, F.FITTING):
            self._text(40 * scale, 36 * scale, f"Dots done {view['done']} of {view['total']}", mid,
                       TEXT, anchor="w")
            self._text(w - 40 * scale, 36 * scale, "Space = rest  ·  Esc = cancel", small, GREY,
                       "normal", anchor="e")
            dot = view["dot"]
            if dot is not None:
                self._draw_dot(dot, now, scale)
            if phase == F.FITTING:
                self._text(w / 2, h / 2, "Checking your calibration…", mid)
        elif phase == F.SUCCESS:
            result = view["result"] or {}
            percent = result.get("accuracy_percent")
            shown = f" – {percent:.1f} %" if percent is not None else ""
            if result.get("low_accuracy"):
                self._text(w / 2, h * 0.4, f"✓ Saved with low accuracy{shown}", big, YELLOW)
                self._text(w / 2, h * 0.52, "Large buttons will work. You can calibrate again later "
                                            "for better accuracy.", mid, SECONDARY, "normal")
            else:
                self._text(w / 2, h * 0.4, f"✓ Calibration complete{shown}", big, GREEN)
                self._text(w / 2, h * 0.52, "Eye tracking is starting…", mid, SECONDARY, "normal")
        elif phase == F.FAILED:
            self._text(w / 2, h * 0.38, f"✗ {view['message'] or 'Calibration did not finish.'}", big, RED)
            if view["message"] == F.LOST:
                self._text(w / 2, h * 0.52, "This window will close.", mid, SECONDARY, "normal")
            elif view["retry_in"] is not None:
                self._text(w / 2, h * 0.52, f"Trying again in {view['retry_in']} s…", mid, YELLOW)
                self._text(w / 2, h * 0.9, "Enter = try now  ·  Esc = stop", small, GREY, "normal")
            else:
                self._text(w / 2, h * 0.52, "Press Enter to try again, or Esc to close.", mid,
                           SECONDARY, "normal")
        if view["advice"] and phase in (F.CHECKING, F.DOTS):
            c.create_rectangle(w * 0.2, h * 0.76, w * 0.8, h * 0.84, fill=PANEL, outline=YELLOW, width=3)
            self._text(w / 2, h * 0.8, f"⚠  {view['advice']}", mid, YELLOW)
        if view["paused"]:
            c.create_rectangle(0, h * 0.42, w, h * 0.58, fill=PANEL, outline="")
            self._text(w / 2, h / 2, "Paused – press Space to continue", big)
        if view["message"] and phase == F.DOTS:
            self._text(w / 2, h * 0.92, view["message"], mid, SECONDARY, "normal")

    def _draw_dot(self, dot: dict, now: float, scale: float) -> None:
        c = self.canvas
        x, y = dot_position((dot["x"], dot["y"]), (self.width, self.height))
        r, ring = DOT_RADIUS * scale, RING_RADIUS * scale
        color = {"accepted": GREEN, "rest": GREY}.get(dot["state"], YELLOW)
        if dot["state"] == "collecting":
            start = (now * 360) % 360
            c.create_arc(x - ring, y - ring, x + ring, y + ring, start=start, extent=270,
                         style="arc", outline=YELLOW, width=max(3, int(6 * scale)))
        else:
            c.create_oval(x - ring, y - ring, x + ring, y + ring, outline=color, width=max(2, int(3 * scale)))
        c.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=BACKGROUND, width=2)
        c.create_oval(x - 4, y - 4, x + 4, y + 4, fill=BACKGROUND, outline="")


def dot_position(point: tuple[float, float], screen: tuple[int, int]) -> tuple[int, int]:
    """Physical-pixel centre of a calibration dot (fractions of the screen, like the engine)."""
    return round(point[0] * screen[0]), round(point[1] * screen[1])

