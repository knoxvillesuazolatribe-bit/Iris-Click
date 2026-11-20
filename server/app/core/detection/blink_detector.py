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

Per-person wink rules (one-eye winks only; both-eye blinks are unchanged):

  * Eye balance: some people's eyelids are naturally uneven, so one eye always
    looks narrower. The detector learns the usual left/right openness ratio from
    open-eye frames and compares the eyes after balancing for it; otherwise that
    person's narrower eye misfires and the other eye's wink is missed.
  * Flicker: one noisy "open" frame in the middle of a wink must not cancel it,
    so a wink that reopens for at most WINK_GAP_S and closes again is one wink.
  * Too long: a one-eye closure longer than MAX_WINK_MS is resting an eye or
    squinting (glare), not a click.
"""

import time
from collections import deque
from statistics import median

# The winking eye must be below this fraction of the open eye. 0.6 gave no
# wink on s1-s5 (users told not to wink); 0.7 fired a false one on s4.
CLOSED_FRACTION = 0.6
# Both eyes count as closed only below this EAR (s4 bottom row: ~0.13 open).
BOTH_CLOSED_EAR = 0.10
# Eye balance (left EAR / right EAR while open): learned from the last
# BALANCE_FRAMES open-eye frames, used after BALANCE_MIN_FRAMES (~2 s), and kept
# within BALANCE_LIMITS so a bad landmark run cannot disable winks on one side.
BALANCE_FRAMES = 150
BALANCE_MIN_FRAMES = 60
BALANCE_LIMITS = (0.7, 1.0 / 0.7)
# Frames teach the balance only while both eyes are clearly open (a winking eye
# is far below this). The median ignores the few partly closed frames of a wink.
BALANCE_OPEN_EAR = 0.15
WINK_GAP_S = 0.08
MAX_WINK_MS = 2000

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
        # (closed_since, kind, reopened_at) of a wink cut short by a flicker.
        self._broken = None
        self._ratios: deque[float] = deque(maxlen=BALANCE_FRAMES)
        self.balance = 1.0

    def classify(self, left_ear, right_ear):
        """The closure this frame shows ('left', 'right', 'both') or None if open."""
        if max(left_ear, right_ear) < BOTH_CLOSED_EAR:
            return BOTH
        # Compare the eyes as if both were the same size when open.
        balanced_right = right_ear * self.balance
        if left_ear < self.threshold and left_ear < CLOSED_FRACTION * balanced_right:
            return LEFT
        if right_ear < self.threshold and balanced_right < CLOSED_FRACTION * left_ear:
            return RIGHT
        return None

    def _learn_balance(self, left_ear, right_ear):
        if min(left_ear, right_ear) < BALANCE_OPEN_EAR:
            return
        self._ratios.append(left_ear / right_ear)
        if len(self._ratios) < BALANCE_MIN_FRAMES:
            return
        if len(self._ratios) == BALANCE_MIN_FRAMES:
            # A "closure" seen before the balance was known may just be the
            # naturally narrower eye; it must not click.
            self.reset()
        self.balance = min(max(median(self._ratios), BALANCE_LIMITS[0]), BALANCE_LIMITS[1])

    def update(self, left_ear, right_ear, now=None):
        """Feed per-eye aspect ratios; return 'left', 'right', 'both' or None."""
        now = time.monotonic() if now is None else now
        self._learn_balance(left_ear, right_ear)
        kind = self.classify(left_ear, right_ear)
        if kind is not None:
            if self._closed_since is None:
                self._closed_since = now
                self._closure_kind = kind
                broken, self._broken = self._broken, None
                if broken is not None and broken[1] == kind and now - broken[2] <= WINK_GAP_S:
                    self._closed_since = broken[0]  # the same wink after a flicker
            elif kind == BOTH:
                # A wink that becomes a full blink is a blink: the second eye
                # closing slightly later is the common case, not a new gesture.
                self._closure_kind = BOTH
            return None

        if self._closed_since is None:
            return None
        duration_ms = (now - self._closed_since) * 1000
        closure_kind = self._closure_kind
        closed_since = self._closed_since
        self._closed_since = None
        self._closure_kind = None
        is_wink = closure_kind in (LEFT, RIGHT)
        if duration_ms < self.consec_ms:
            if is_wink:
                self._broken = (closed_since, closure_kind, now)
            return None
        if is_wink and duration_ms > MAX_WINK_MS:
            return None
        if (now - self._last_trigger) * 1000 < self.cooldown_ms:
            return None
        self._last_trigger = now
        return closure_kind

    def reset(self):
        """Forget the closure in progress; the learned eye balance is the person's and stays."""
        self._closed_since = None
        self._closure_kind = None
        self._broken = None
