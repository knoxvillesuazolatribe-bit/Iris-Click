"""Dwell-time click: fire once the gaze holds still within a radius.

Answers the "Midas touch" problem: looking around never clicks by itself, and
the gaze must leave the radius before another click can be armed.
"""

import math
import time


class DwellClicker:
    def __init__(self, radius_px=40.0, dwell_ms=700, cooldown_ms=250):
        self.radius_px = radius_px
        self.dwell_ms = dwell_ms
        self.cooldown_ms = cooldown_ms
        self._anchor = None
        self._dwell_start = None
        self._armed = True
        self._last_click_time = 0.0

    def reset(self):
        self._anchor = None
        self._dwell_start = None
        self._armed = True

    def progress(self) -> float:
        """Completion ratio in [0, 1] for the progress ring; 0 once fired."""
        if self._dwell_start is None or not self._armed:
            return 0.0
        elapsed_ms = (time.monotonic() - self._dwell_start) * 1000
        return min(1.0, elapsed_ms / self.dwell_ms)

    def update(self, x, y) -> bool:
        """Return True exactly when a click should fire."""
        now = time.monotonic()
        if self._anchor is None:
            self._anchor = (x, y)
            self._dwell_start = now
            return False
        if math.hypot(x - self._anchor[0], y - self._anchor[1]) > self.radius_px:
            self._anchor = (x, y)
            self._dwell_start = now
            self._armed = True
            return False
        if not self._armed:
            return False
        if (now - self._dwell_start) * 1000 >= self.dwell_ms:
            if (now - self._last_click_time) * 1000 >= self.cooldown_ms:
                self._armed = False
                self._last_click_time = now
                return True
        return False
