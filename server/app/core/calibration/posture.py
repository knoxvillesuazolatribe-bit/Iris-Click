"""Detects that the user now sits differently from when the mapping was fitted.

On recordings s2-s5 the error of a mapping fitted in one sitting and used in
another was 107-141 px when the head stayed put, but 280-365 px after leaning
back (eye spacing -37%) or turning the head ~3.5 deg; a 5-dot re-centre in
the new sitting brought those back to 96-217 px. So the worker asks for a
re-centre once a shift like that persists.
"""

import math
from collections import deque

import numpy as np

from app.schemas.calibration import PostureReference

# s2->s3 (11% closer, 1.5 deg) transferred fine; s4->s5 (37%) and s3->s4
# (3.5 deg) did not. Tuned on those four sittings only.
MAX_DISTANCE_CHANGE = 0.15
MAX_ANGLE_CHANGE = math.radians(3.0)
# Looking at a screen corner turns the head too; a long median ignores that.
WINDOW_S = 6.0
MIN_SAMPLES = 30
# The shift must last this long before the user is asked to re-centre.
SUSTAIN_S = 3.0


def posture_of(reading) -> PostureReference | None:
    """The head posture of one tracker reading, or None without a face."""
    if not reading.face_found or not reading.eye_line or reading.features is None:
        return None
    spacing = reading.eye_line.get("eye_distance", 0.0)
    if not spacing or spacing <= 0:
        return None
    return PostureReference(eye_distance=spacing, yaw=reading.features[4],
                            pitch=reading.features[5])


def median_posture(postures) -> PostureReference | None:
    values = np.array([(p.eye_distance, p.yaw, p.pitch) for p in postures if p is not None])
    if len(values) < MIN_SAMPLES:
        return None
    spacing, yaw, pitch = np.median(values, axis=0)
    return PostureReference(eye_distance=float(spacing), yaw=float(yaw), pitch=float(pitch))


def posture_change(reference: PostureReference, current: PostureReference) -> str | None:
    """"distance", "angle" or None when ``current`` still matches ``reference``."""
    if abs(current.eye_distance / reference.eye_distance - 1.0) > MAX_DISTANCE_CHANGE:
        return "distance"
    turn = math.hypot(current.yaw - reference.yaw, current.pitch - reference.pitch)
    if turn > MAX_ANGLE_CHANGE:
        return "angle"
    return None


class PostureMonitor:
    """Running posture versus the reference the active mapping was fitted in.

    ``now`` is any monotonic clock in seconds.
    """

    def __init__(self, reference: PostureReference | None = None):
        self.reference = reference
        self._samples: deque[tuple[float, PostureReference]] = deque()
        self._changed_since: float | None = None
        self.change: str | None = None

    def set_reference(self, reference: PostureReference | None):
        self.reference = reference
        self._changed_since = None
        self.change = None

    def current(self) -> PostureReference | None:
        return median_posture([p for _, p in self._samples])

    def update(self, now: float, reading) -> bool:
        """Feed a reading; True once when a sustained posture change begins."""
        posture = posture_of(reading)
        if posture is not None:
            self._samples.append((now, posture))
        while self._samples and now - self._samples[0][0] > WINDOW_S:
            self._samples.popleft()
        current = self.current()
        if self.reference is None or current is None:
            return False
        change = posture_change(self.reference, current)
        if change is None:
            self._changed_since = None
            self.change = None
            return False
        if self._changed_since is None:
            self._changed_since = now
        if self.change is None and now - self._changed_since >= SUSTAIN_S:
            self.change = change
            return True
        return False
