"""Intentional-blink detection: left-eye wink, right-eye wink, both eyes.

Blinks are a command channel, so natural blinking must never fire a command:

  * Duration gate: a natural blink lasts roughly 100-150 ms, so a closure only
    counts once the eye has stayed closed for ``consec_ms``.
  * Wink disambiguation: a one-eyed wink is only reported when the other eye
    is clearly open (``OPEN_MARGIN``). Without that margin a slightly uneven
    ordinary blink would misfire as a wink.

At most one event is emitted per closure, on reopening, so holding the eyes
shut does not repeat the command.
"""

import time

# The open eye must exceed the closed threshold by this factor before a
# one-eyed closure is trusted as a deliberate wink.
OPEN_MARGIN = 1.6

BOTH = "both"
LEFT = "left"
RIGHT = "right"


class BlinkDetector:
    def __init__(self, threshold=0.18, consec_ms=350, cooldown_ms=700):
        self.threshold = threshold
        self.consec_ms = consec_ms
        self.cooldown_ms = cooldown_ms
        self._closed_since = None
        self._closure_kind = None
        self._last_trigger = float("-inf")

    def _classify(self, left_ear, right_ear):
        left_closed = left_ear < self.threshold
        right_closed = right_ear < self.threshold
        if left_closed and right_closed:
            return BOTH
        if left_closed and right_ear > self.threshold * OPEN_MARGIN:
            return LEFT
        if right_closed and left_ear > self.threshold * OPEN_MARGIN:
            return RIGHT
        return None

    def update(self, left_ear, right_ear, now=None):
        """Feed per-eye aspect ratios; return 'left', 'right', 'both' or None."""
        now = time.monotonic() if now is None else now
        kind = self._classify(left_ear, right_ear)
        if kind is not None:
            if self._closed_since is None:
                self._closed_since = now
                self._closure_kind = kind
            elif kind == BOTH:
                # A wink that becomes a full blink is a blink: the second eye
                # closing slightly later is the common case, not a new gesture.
                self._closure_kind = BOTH
            return None

        if self._closed_since is None:
            return None
        duration_ms = (now - self._closed_since) * 1000
        closure_kind = self._closure_kind
        self._closed_since = None
        self._closure_kind = None
        if duration_ms < self.consec_ms:
            return None
        if (now - self._last_trigger) * 1000 < self.cooldown_ms:
            return None
        self._last_trigger = now
        return closure_kind

    def reset(self):
        self._closed_since = None
        self._closure_kind = None
