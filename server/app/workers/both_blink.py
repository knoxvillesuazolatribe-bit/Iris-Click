"""Single vs double both-eye blink (team decision D2, Phase 9).

One deliberate both-eye blink takes a screenshot; two within DOUBLE_WINDOW_S
open or close the on-screen keyboard. The blink detector refuses a second
event within 0.7 s, so a double blink naturally takes about 1-1.8 s. The
screenshot therefore waits out the window: if a second blink arrives in time,
only the keyboard toggles and no screenshot is taken.
"""

from collections.abc import Callable

DOUBLE_WINDOW_S = 1.8
SINGLE, DOUBLE, PENDING, IGNORED = "screenshot", "keyboard", "waiting for a second blink", "ignored"


class BothBlinkRouter:
    def __init__(self, schedule: Callable[[int, Callable[[], None]], object],
                 cancel: Callable[[object], None],
                 on_single: Callable[[], None], on_double: Callable[[], None],
                 window_s: float = DOUBLE_WINDOW_S):
        """``schedule(ms, fn)`` / ``cancel(handle)``: e.g. Tk's after / after_cancel."""
        self._schedule, self._cancel = schedule, cancel
        self._on_single, self._on_double = on_single, on_double
        self.window_s = window_s
        self._first_at: float | None = None
        self._job = None

    @property
    def waiting(self) -> bool:
        return self._first_at is not None

    def blink(self, now: float) -> str:
        """A deliberate both-eye blink happened at ``now``; returns what it did."""
        if self._first_at is not None and now - self._first_at <= self.window_s:
            self._clear()
            self._on_double()
            return DOUBLE
        self._clear()
        self._first_at = now
        self._job = self._schedule(int(self.window_s * 1000), self._expire)
        return PENDING

    def _expire(self) -> None:
        self._first_at, self._job = None, None
        self._on_single()

    def _clear(self) -> None:
        if self._job is not None:
            try:
                self._cancel(self._job)
            except Exception:  # noqa: BLE001 - already fired
                pass
        self._first_at, self._job = None, None
