"""Where the user was looking just before an eyelid started to close.

A closing lid drags the iris landmarks down for ~100 ms before the eye counts
as closed, and smoothing adds similar latency, so the cursor at "eye closed" is
already off target. The cursor is recorded with the eye openness of the frame
it came from; a wink clicks at the last point recorded while both eyes were
still fully open.
"""

from collections import deque

from app.core.detection.blink_detector import BOTH_CLOSED_EAR

HISTORY_S = 1.5
# An eye below this fraction of its usual openness counts as "lid moving".
OPEN_RATIO = 0.85
# Eyes within this ratio of each other move together (gaze shift or blink);
# a closing wink eye falls below it.
TOGETHER_RATIO = 0.85
# Per-frame step of the open-eye estimate toward the current, symmetric
# openness. Looking down narrows both eyes for as long as the gaze stays low
# (s1-s5: ~0.31 top row, ~0.13 taskbar row), so the estimate follows within
# ~20 frames; a 100-150 ms blink moves it only a few percent.
BASELINE_ALPHA = 0.1


class BlinkAnchor:
    def __init__(self):
        self._history: deque[tuple[float, float, float, float, bool]] = deque()
        self._open_ear: float | None = None

    def reset(self):
        self._history.clear()

    def record(self, timestamp: float, x: float, y: float, left_ear: float, right_ear: float):
        lower, upper = min(left_ear, right_ear), max(left_ear, right_ear)
        together = lower >= upper * TOGETHER_RATIO
        if self._open_ear is None:
            self._open_ear = upper
        elif together and upper >= BOTH_CLOSED_EAR:
            self._open_ear += BASELINE_ALPHA * (upper - self._open_ear)
        self._history.append((timestamp, x, y, lower, together))
        while self._history and timestamp - self._history[0][0] > HISTORY_S:
            self._history.popleft()

    def anchor(self) -> tuple[float, float] | None:
        """The latest cursor point recorded while both eyes were fully open."""
        if self._open_ear is None:
            return None
        threshold = self._open_ear * OPEN_RATIO
        for _, x, y, ear, together in reversed(self._history):
            if together and ear >= threshold:
                return x, y
        return None
