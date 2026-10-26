"""Snap an imprecise gaze point onto the button the user is aiming at.

Webcam gaze resolves a region (~4-8% of the screen), not a pixel; small
controls like a browser tab's close "X" are smaller than that error. Given the
actionable rectangles on screen, the pointer locks onto the nearest one and
stays there until the gaze clearly moves to another control or away.
"""

import math
from dataclasses import dataclass

# Pre-aim lock tuned in the original IrisClick: switch to another control only
# after the gaze rests on (or clearly nearer to) it for SWITCH_SECONDS; release
# to free movement after RELEASE_SECONDS of looking well away.
SWITCH_SECONDS = 0.15
RELEASE_SECONDS = 0.35
STICKY_RADIUS_FACTOR = 1.35
SWITCH_HYSTERESIS_PX = 40.0


@dataclass(frozen=True)
class TargetRect:
    left: int
    top: int
    right: int
    bottom: int
    name: str = ""

    @property
    def width(self):
        return self.right - self.left

    @property
    def height(self):
        return self.bottom - self.top

    @property
    def center(self):
        return (self.left + self.right) / 2.0, (self.top + self.bottom) / 2.0

    def distance_to(self, x, y):
        dx = max(self.left - x, 0.0, x - self.right)
        dy = max(self.top - y, 0.0, y - self.bottom)
        return math.hypot(dx, dy)


def choose_target(x, y, targets, radius):
    """The most plausible actionable target within ``radius`` px, or None."""
    best = None
    for target in targets:
        edge_distance = target.distance_to(x, y)
        if edge_distance > radius:
            continue
        cx, cy = target.center
        # Edge distance decides who owns nearby whitespace; the small centre and
        # area terms break ties between nested or overlapping controls.
        score = (edge_distance + math.hypot(cx - x, cy - y) * 0.06
                 + target.width * target.height * 0.00001)
        key = (score, target.width * target.height)
        if best is None or key < best[0]:
            best = (key, target)
    return best[1] if best else None


class TargetLock:
    def __init__(self, radius=140.0):
        self.radius = float(radius)
        self.reset()

    def reset(self):
        self.active = None
        self._switch_to = None
        self._switch_since = None
        self._away_since = None

    def snap(self, x, y, targets, now):
        """Return (x, y, target): the locked target's centre, or the gaze point."""
        nearest = choose_target(x, y, targets, self.radius)
        active = self.active if self.active in targets else None
        if active is None:
            self.reset()
            self.active = nearest
        else:
            active_distance = active.distance_to(x, y)
            rival = None
            if nearest is not None and nearest != active:
                nearest_distance = nearest.distance_to(x, y)
                if nearest_distance == 0.0 or nearest_distance + SWITCH_HYSTERESIS_PX < active_distance:
                    rival = nearest
            if rival is None:
                self._switch_to = self._switch_since = None
            elif rival != self._switch_to:
                self._switch_to, self._switch_since = rival, now
            if rival is not None and now - self._switch_since >= SWITCH_SECONDS:
                self.reset()
                self.active = rival
            elif active_distance <= self.radius * STICKY_RADIUS_FACTOR or rival is not None:
                self._away_since = None
            else:
                if self._away_since is None:
                    self._away_since = now
                if now - self._away_since >= RELEASE_SECONDS:
                    self.reset()
        if self.active is None:
            return x, y, None
        sx, sy = self.active.center
        return sx, sy, self.active
