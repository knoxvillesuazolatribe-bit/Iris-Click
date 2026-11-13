"""Reserve a strip at the top of the screen for the IrisClick control bar, like the Windows taskbar.

Without it the bar floats over maximised windows and hides a browser's address bar and tabs (found
in testing: the user could not reach Google's search box under the bar). Registered as a Windows
"app bar", the strip is taken out of the work area, so maximised windows start just below the bar.
The strip is released when the bar is dragged away and when IrisClick exits.
"""

import atexit
import ctypes
import ctypes.wintypes
import logging
from collections.abc import Callable

logger = logging.getLogger("irisclick.appbar")

ABM_NEW, ABM_REMOVE, ABM_QUERYPOS, ABM_SETPOS = 0, 1, 2, 3
ABE_TOP = 1
CALLBACK_MESSAGE = 0x0400 + 0x1C1  # WM_USER + n: Windows' notices to the bar (not needed, but required)


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.wintypes.DWORD), ("hWnd", ctypes.wintypes.HWND),
                ("uCallbackMessage", ctypes.wintypes.UINT), ("uEdge", ctypes.wintypes.UINT),
                ("rc", ctypes.wintypes.RECT), ("lParam", ctypes.wintypes.LPARAM)]


def _shell_message(message: int, data: APPBARDATA) -> int:
    return ctypes.windll.shell32.SHAppBarMessage(message, ctypes.byref(data))


class TopStrip:
    """The reserved strip for one window: ``dock(height)`` claims it, ``release()`` gives it back."""

    def __init__(self, hwnd: int, screen_w: int, send: Callable[[int, APPBARDATA], int] = _shell_message):
        self.hwnd, self.screen_w, self._send = hwnd, screen_w, send
        self.registered = False
        self.height = 0

    def _data(self, height: int) -> APPBARDATA:
        data = APPBARDATA()
        data.cbSize = ctypes.sizeof(APPBARDATA)
        data.hWnd = self.hwnd
        data.uCallbackMessage = CALLBACK_MESSAGE
        data.uEdge = ABE_TOP
        data.rc = ctypes.wintypes.RECT(0, 0, self.screen_w, height)
        return data

    def dock(self, height: int) -> bool:
        """Reserve ``height`` px at the top of the main screen. False if Windows refuses (the bar still works)."""
        try:
            if not self.registered:
                if not self._send(ABM_NEW, self._data(height)):
                    return False
                self.registered = True
            data = self._data(height)
            self._send(ABM_QUERYPOS, data)  # Windows may move the strip below another app bar
            data.rc.bottom = data.rc.top + height
            self._send(ABM_SETPOS, data)
            self.height = height
            return True
        except Exception:  # noqa: BLE001 - an enhancement only: never stop eye tracking for it
            logger.warning("Could not reserve the top of the screen for the control bar", exc_info=True)
            return False

    def release(self) -> None:
        if not self.registered:
            return
        try:
            self._send(ABM_REMOVE, self._data(0))
        except Exception:  # noqa: BLE001
            logger.warning("Could not release the top of the screen", exc_info=True)
        self.registered = False
        self.height = 0


def reserve_top(hwnd: int, screen_w: int, height: int) -> TopStrip:
    """Claim the strip now and release it automatically when IrisClick exits."""
    strip = TopStrip(hwnd, screen_w)
    strip.dock(height)
    atexit.register(strip.release)
    return strip
