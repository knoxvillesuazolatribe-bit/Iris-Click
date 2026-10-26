"""Gaze places the cursor coarsely; small head turns fine-tune it.

MAGIC pointing (Zhai et al., CHI 1999) with the head instead of a hand: webcam
gaze is only accurate to ~90 px, but the nose apex of the "0 V 0" pyramid is a
large, steady landmark. Each time the gaze settles on a new fixation, the
current apex becomes the reference; turning the head from there offsets the
cursor proportionally. A new gaze jump resets the offset, so it never
accumulates.
"""

import math

from app.core.gaze.smoothing import OneEuroFilter2D

# Pixels of cursor offset per eye-distance unit of nose-apex movement. A 2-degree
# head turn moves the apex ~0.02 eye distances, giving ~60 px.
DEFAULT_GAIN_PX = 3000.0
# Landmark jitter on the apex is ~0.003 eye distances (~9 px at this gain);
# ignore movement below the deadband so a still head never drifts the cursor.
DEADBAND = 0.006
# Beyond this the user should simply look at the new place.
DEFAULT_MAX_OFFSET_PX = 200.0


def _soft_deadband(value: float) -> float:
    return math.copysign(max(0.0, abs(value) - DEADBAND), value)


class HeadNudge:
    def __init__(self, gain_px=DEFAULT_GAIN_PX, max_offset_px=DEFAULT_MAX_OFFSET_PX):
        self.gain_px = float(gain_px)
        self.max_offset_px = float(max_offset_px)
        self._filter = OneEuroFilter2D(freq=30.0, mincutoff=1.0, beta=0.5)
        self.reset()

    def reset(self):
        self._reference = None
        self._anchor_id = None
        self._filter.reset()

    def update(self, apex, anchor_id, timestamp):
        """Return the (dx, dy) cursor offset for the current nose apex.

        ``apex`` is the (x, y) nose apex in eye-distance units, or None when
        the face is not visible; ``anchor_id`` changes on every new fixation.
        """
        if apex is None:
            return 0.0, 0.0
        ax, ay = self._filter(float(apex[0]), float(apex[1]), timestamp=timestamp)
        if anchor_id != self._anchor_id or self._reference is None:
            self._anchor_id = anchor_id
            self._reference = (ax, ay)
            return 0.0, 0.0
        dx = _soft_deadband(ax - self._reference[0]) * self.gain_px
        dy = _soft_deadband(ay - self._reference[1]) * self.gain_px
        length = math.hypot(dx, dy)
        if length > self.max_offset_px:
            scale = self.max_offset_px / length
            dx, dy = dx * scale, dy * scale
        return dx, dy
