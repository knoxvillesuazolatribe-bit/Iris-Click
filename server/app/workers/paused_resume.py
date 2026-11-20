"""Security/safety audit: a hands-free way out of "Paused".

While tracking is paused the gaze cursor is hidden and winks do nothing, so a person who
cannot use a mouse could not reach the Resume button. Two both-eye blinks in a row
(the same double blink that opens the keyboard, within both_blink.DOUBLE_WINDOW_S)
resume tracking. One blink alone does nothing, so resting eyes never resume by accident.
"""

from app.workers.both_blink import DOUBLE_WINDOW_S

RESUME_HINT = "Blink both eyes twice to resume."


class PausedResume:
    def __init__(self, window_s: float = DOUBLE_WINDOW_S):
        self.window_s = window_s
        self._first_at: float | None = None

    def both_blink(self, now: float) -> bool:
        """A both-eye blink while paused; True when it is the second one in time (resume)."""
        if self._first_at is not None and now - self._first_at <= self.window_s:
            self._first_at = None
            return True
        self._first_at = now
        return False

    def reset(self) -> None:
        self._first_at = None
