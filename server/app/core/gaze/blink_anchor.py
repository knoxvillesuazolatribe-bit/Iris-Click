"""Where the user was looking just before an eyelid started to close.

A closing lid drags the iris landmarks down for ~100 ms before the eye counts
as closed, and smoothing adds similar latency, so the cursor at "eye closed" is
already off target. The cursor is recorded with the eye openness of the frame
it came from; a wink clicks at the last point recorded while both eyes were
still fully open.
"""

from collections import deque

HISTORY_S = 1.5
# An eye below this fraction of its usual openness counts as "lid moving".
OPEN_RATIO = 0.85
# Slow running estimate of a fully open eye's EAR, learned per user.
BASELINE_ALPHA = 0.02


class BlinkAnchor:
    def __init__(self):
        self._history: deque[tuple[float, float, float, float]] = deque()
        self._open_ear: float | None = None

    def reset(self):
        self._history.clear()

    def record(self, timestamp: float, x: float, y: float, ear: float):
        """``ear``: the lower of the two eyes' aspect ratios for this frame."""
        if self._open_ear is None:
            self._open_ear = ear
        elif ear >= self._open_ear * OPEN_RATIO:
            self._open_ear += BASELINE_ALPHA * (ear - self._open_ear)
        self._history.append((timestamp, x, y, ear))
        while self._history and timestamp - self._history[0][0] > HISTORY_S:
            self._history.popleft()

    def anchor(self) -> tuple[float, float] | None:
        """The latest cursor point recorded while both eyes were fully open."""
        if self._open_ear is None:
            return None
        threshold = self._open_ear * OPEN_RATIO
        for _, x, y, ear in reversed(self._history):
            if ear >= threshold:
                return x, y
        return None
