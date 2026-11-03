"""Intentional-blink detection: left-eye wink, right-eye wink, both eyes.

Blinks are a command channel, so natural blinking must never fire a command:

  * Duration gate: a natural blink lasts roughly 100-150 ms, so a closure only
    counts once the eye has stayed closed for ``consec_ms``.
  * Wink disambiguation: a one-eyed wink is only reported when the closing eye
    is well below the other one (``CLOSED_FRACTION``). Without that margin a
    slightly uneven ordinary blink would misfire as a wink.

Looking down narrows both eyes alike: on recordings s1-s5 the two eyes'
EAR stayed within 0.01 of each other on every screen row while the row
median fell from ~0.31 (top) to ~0.13 (taskbar). Fixed levels therefore
read a low gaze as "closed" (cursor frozen on 96% of bottom-row frames in s4)
and refused winks below mid-screen (old rule: other eye > 0.29), so eyes
are compared with each other, and "both closed" is an absolute floor below
any open-eye level seen.

At most one event is emitted per closure, on reopening, so holding the eyes
shut does not repeat the command.
"""

import time

# The winking eye must be below this fraction of the open eye. 0.6 gave no
# wink on s1-s5 (users told not to wink); 0.7 fired a false one on s4.
CLOSED_FRACTION = 0.6
# Both eyes count as closed only below this EAR (s4 bottom row: ~0.13 open).
BOTH_CLOSED_EAR = 0.10

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

    def classify(self, left_ear, right_ear):
        """The closure this frame shows ('left', 'right', 'both') or None if open."""
        if max(left_ear, right_ear) < BOTH_CLOSED_EAR:
            return BOTH
        if left_ear < self.threshold and left_ear < CLOSED_FRACTION * right_ear:
            return LEFT
        if right_ear < self.threshold and right_ear < CLOSED_FRACTION * left_ear:
            return RIGHT
        return None

    def update(self, left_ear, right_ear, now=None):
        """Feed per-eye aspect ratios; return 'left', 'right', 'both' or None."""
        now = time.monotonic() if now is None else now
        kind = self.classify(left_ear, right_ear)
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
