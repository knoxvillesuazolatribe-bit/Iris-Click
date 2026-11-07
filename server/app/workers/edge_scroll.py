"""Edge scroll: look at the top or bottom band of the screen to scroll.

Called once per drawn cursor position from tracking_worker (hook H4c). The
gaze must stay in a band for the dwell time before scrolling starts; it then
scrolls one wheel notch every SCROLL_EVERY_S until the gaze leaves.

Nothing is called while tracking is paused, the mouse is in use, a re-centre
runs or the eyes are closing, so those never scroll; a gap in calls resets
the timer. This is vertical only and separate from edge_reach, which shapes
left/right cursor reach.

The wheel goes to the window in the middle of the screen at the gaze's x, not
to the cursor: at the top edge the cursor is usually on the browser's tab bar,
where a wheel does not scroll the page. The cursor itself never moves.
"""

import ctypes
import logging
import sys
import time
from collections.abc import Callable

from app.config import Settings

logger = logging.getLogger("irisclick.worker.edge_scroll")

UP, DOWN = "up", "down"
SCROLL_EVERY_S = 0.2
# No cursor update for this long (paused, eyes closed…): start the dwell again.
GAP_RESET_S = 0.3
WHEEL_DELTA = 120
WM_MOUSEWHEEL = 0x020A

Rect = tuple[int, int, int, int]  # left, top, right, bottom


def post_wheel(x: int, y: int, notches: int) -> bool:
    """Posts a wheel message to the window under (x, y) without moving the cursor.

    Falls back to an ordinary wheel at the cursor if no window takes it.
    """
    try:
        if sys.platform == "win32":
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.WindowFromPoint.restype = wintypes.HWND
            user32.WindowFromPoint.argtypes = [wintypes.POINT]
            user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                            wintypes.LPARAM]
            hwnd = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
            if hwnd:
                delta = ctypes.c_ushort(WHEEL_DELTA * notches & 0xFFFF).value
                wparam = delta << 16
                lparam = ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)
                if user32.PostMessageW(hwnd, WM_MOUSEWHEEL, wparam, lparam):
                    return True
        import pyautogui

        pyautogui.scroll(WHEEL_DELTA * notches)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Edge scroll wheel failed")
        return False


class EdgeScroller:
    def __init__(self, settings: Settings, screen_w: int, screen_h: int,
                 exclude: Callable[[], list[Rect]] = list,
                 wheel: Callable[[int, int, int], bool] = post_wheel,
                 on_scroll: Callable[[str, int, int], None] | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.enabled = settings.edge_scroll_enabled
        self.screen_w, self.screen_h = screen_w, screen_h
        self.band_px = max(1, round(screen_h * settings.edge_scroll_band))
        self.dwell_s = settings.dwell_ms / 1000.0
        self.exclude = exclude
        self.wheel = wheel
        self.on_scroll = on_scroll
        self.clock = clock
        self._zone: str | None = None
        self._since = 0.0
        self._next_scroll = 0.0
        self._last_update: float | None = None

    def zone(self, x: float, y: float) -> str | None:
        if y < self.band_px:
            direction = UP
        elif y >= self.screen_h - self.band_px:
            direction = DOWN
        else:
            return None
        for left, top, right, bottom in self.exclude():
            if left <= x < right and top <= y < bottom:
                return None
        return direction

    def update(self, x: float, y: float, now: float | None = None) -> str | None:
        """Feeds the shown cursor position; returns the direction scrolled now, if any."""
        if not self.enabled:
            return None
        now = self.clock() if now is None else now
        if self._last_update is not None and now - self._last_update > GAP_RESET_S:
            self._zone = None
        self._last_update = now

        zone = self.zone(x, y)
        if zone != self._zone:
            self._zone, self._since = zone, now
            self._next_scroll = now + self.dwell_s
        if zone is None or now < self._next_scroll:
            return None
        self._next_scroll = now + SCROLL_EVERY_S
        middle_x = int(min(max(x, 0), self.screen_w - 1))
        self.wheel(middle_x, self.screen_h // 2, 1 if zone == UP else -1)
        if self.on_scroll is not None:
            self.on_scroll(zone, self.band_px, int(SCROLL_EVERY_S * 2000))
        return zone
