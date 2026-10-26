"""Notification-area icon for the tracking worker.

pystray runs its own message loop on a separate thread, so menu actions are
only queued here; the worker's Tk thread drains the shared ``commands`` queue.
"""

import queue

import pystray
from PIL import Image, ImageDraw

ICON_SIZE = 64
NAVY = "#0F1B2D"
WHITE = "#FFFFFF"
YELLOW = "#FFD23F"
GREY = "#8A96A8"
RED = "#FF6B6B"

PAUSE = "pause"
TOGGLE_VOICE = "toggle_voice"
RECALIBRATE = "recalibrate"
QUIT = "quit"


def _eye_icon(iris_colour: str) -> Image.Image:
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((0, 0, ICON_SIZE - 1, ICON_SIZE - 1), fill=NAVY)
    draw.ellipse((8, 20, ICON_SIZE - 9, ICON_SIZE - 21), fill=WHITE)
    draw.ellipse((22, 22, 42, 42), fill=iris_colour)
    draw.ellipse((28, 28, 36, 36), fill=NAVY)
    return image


class SystemTray:
    def __init__(self, commands: "queue.Queue[str]"):
        self.commands = commands
        self._status = "IrisClick: starting"
        self._paused = False
        self._voice_enabled = True
        self._icons = {"tracking": _eye_icon(YELLOW), "paused": _eye_icon(GREY),
                       "problem": _eye_icon(RED)}
        self._icon = pystray.Icon(
            "IrisClick",
            icon=self._icons["tracking"],
            title=self._status,
            menu=pystray.Menu(
                pystray.MenuItem(lambda _item: self._status, None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Pause tracking", self._queue(PAUSE), default=True,
                                 checked=lambda _item: self._paused),
                pystray.MenuItem("Voice guidance", self._queue(TOGGLE_VOICE),
                                 checked=lambda _item: self._voice_enabled),
                pystray.MenuItem("Recalibrate…", self._queue(RECALIBRATE)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit IrisClick", self._queue(QUIT)),
            ),
        )

    def _queue(self, command: str):
        def handler(_icon, _item):
            self.commands.put(command)
        return handler

    def start(self):
        self._icon.run_detached()

    def stop(self):
        self._icon.stop()

    def set_state(self, status: str, kind: str, paused: bool, voice_enabled: bool):
        """kind: "tracking", "paused" or "problem"."""
        state = (status, paused, voice_enabled)
        if state == (self._status, self._paused, self._voice_enabled):
            return
        self._status, self._paused, self._voice_enabled = state
        # Windows caps tray tooltips at 127 characters.
        self._icon.title = status[:127]
        self._icon.icon = self._icons[kind]
        self._icon.update_menu()
