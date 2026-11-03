"""Cursor navigation modes: every stage between the calibrated gaze point and
the cursor position handed to the OS.

``legacy``    pipeline feature EMA + One Euro -> fixation lock (80 px, 12-sample
              mean) -> head fine-tune and target snap when enabled. The
              behaviour before modes existed; the default until benchmarks
              say otherwise.
``raw``       newest frame's calibrated prediction, unfiltered: the latency
              and jitter baseline.
``filtered``  adaptive One Euro on the raw prediction, nothing else.
``head``      ``filtered`` + head fine-tune; the head reference resets on
              every gaze jump.
``assisted``  ``filtered`` + optional light fixation assist + target snapping.
``steer``     eyes move the cursor (``filtered``); once the gaze rests, the eye
              estimate freezes and small head movements steer the cursor for
              the last ~100 px (head jitter 4-8 px vs 50-105 px for the eyes,
              recordings s2/s3). A quick eye jump returns to free gaze. The
              Project GameFace approach (Google, 2023) applied to fine aim.
              Snapping runs only in fine aim: during free gaze it would catch
              every control the eyes pass over.

Coordinates are physical screen pixels; timestamps are the camera's
``captured_at`` (perf_counter s) except ``now`` for target snapping, which
only needs a consistent clock.
"""

import math
from collections import deque
from dataclasses import dataclass, replace

from app.core.actions.target_snap import TargetLock, TargetRect
from app.core.gaze.edge_reach import EDGE_LEVELS, apply_edge_reach
from app.core.gaze.head_nudge import HeadNudge
from app.core.gaze.smoothing import GazeStabilizer, OneEuroFilter2D

MODES = ("legacy", "raw", "filtered", "head", "assisted", "steer")

# Legacy fixation-lock radius at smoothing 0 and the extra range up to
# smoothing 1. Measured webcam jitter is ~30 px/frame with 100-160 px steps,
# so the default smoothing (0.25) locks within 80 px.
FIXATION_RADIUS_MIN_PX = 40.0
FIXATION_RADIUS_RANGE_PX = 160.0


@dataclass(frozen=True)
class NavigationConfig:
    mode: str = "legacy"
    # Legacy lock radius; in ``head`` mode only the gaze-jump detector.
    fixation_radius_px: float = 80.0
    filter_mincutoff: float = 0.8
    filter_beta: float = 0.01
    filter_dcutoff: float = 1.0
    assist_enabled: bool = True
    assist_radius_px: float = 50.0
    # ~270 ms at 22 fps, half the legacy 12-sample window.
    assist_window: int = 6
    # head_enabled only applies to ``legacy`` and snap_enabled to ``legacy`` and
    # ``steer``; the other modes define their own stages.
    edge_sensitivity: str = "off"
    head_enabled: bool = True
    head_gain_px: float = 3000.0
    head_max_px: float = 200.0
    snap_enabled: bool = True
    snap_radius_px: float = 140.0
    # Tiny landmark fluctuations must not vibrate the OS cursor or keep
    # re-anchoring the dwell timer.
    deadzone_px: float = 4.0
    # ``steer``: the gaze rests once steer_settle_share of its samples over
    # steer_settle_s lie within steer_settle_radius_px of their mean (eye
    # noise of 50-105 px broke an all-samples test: on s3 30% of fixation
    # frames never settled). It leaves fine aim on a jump of
    # steer_exit_radius_px made within steer_exit_s (a saccade; head turns
    # drift the eye estimate slowly) that still holds after steer_exit_hold_s
    # (brief bad estimates caused 32% of the cursor motion on s3; a frame
    # count is not enough because the camera delivers frames in ~12 ms bursts).
    steer_settle_radius_px: float = 100.0
    steer_settle_share: float = 0.8
    steer_settle_s: float = 0.25
    steer_exit_radius_px: float = 200.0
    steer_exit_s: float = 0.15
    steer_exit_hold_s: float = 0.1
    steer_max_px: float = 300.0
    # The head keeps turning for a few hundred ms after the eyes land on a
    # target; head steering starts only once the nose apex has stayed within
    # this radius (eye-distance units, ~2x its jitter) for steer_head_still_s.
    steer_head_still: float = 0.008
    steer_head_still_s: float = 0.25

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"Unknown gaze mode {self.mode!r}; expected one of {MODES}.")
        if self.edge_sensitivity not in EDGE_LEVELS:
            raise ValueError(f"Unknown edge sensitivity {self.edge_sensitivity!r}; "
                             f"expected one of {EDGE_LEVELS}.")

    @property
    def uses_head(self) -> bool:
        return self.mode in ("head", "steer") or (self.mode == "legacy" and self.head_enabled)

    @property
    def uses_targets(self) -> bool:
        return self.mode == "assisted" or (self.mode in ("legacy", "steer") and self.snap_enabled)

    @property
    def glides(self) -> bool:
        return self.mode != "raw"

    @classmethod
    def from_settings(cls, settings, **overrides) -> "NavigationConfig":
        values = dict(
            mode=settings.gaze_mode,
            fixation_radius_px=(FIXATION_RADIUS_MIN_PX
                                + settings.cursor_smoothing * FIXATION_RADIUS_RANGE_PX),
            filter_mincutoff=settings.gaze_filter_mincutoff,
            filter_beta=settings.gaze_filter_beta,
            assist_enabled=settings.fixation_assist_enabled,
            assist_radius_px=settings.fixation_assist_radius_px,
            head_enabled=settings.head_fine_tune_enabled,
            head_gain_px=settings.head_fine_tune_gain_px,
            head_max_px=settings.head_fine_tune_max_px,
            snap_enabled=settings.target_snap_enabled,
            snap_radius_px=settings.target_snap_radius_px,
            edge_sensitivity=settings.edge_sensitivity,
        )
        values.update(overrides)
        return cls(**values)


@dataclass(frozen=True)
class NavigationStep:
    x: float
    y: float
    target: TargetRect | None = None
    head_offset_px: float = 0.0
    # True while ``steer`` is in head fine-aim.
    fine: bool = False


class CursorNavigator:
    def __init__(self, config: NavigationConfig, screen_w: int, screen_h: int):
        self.config = config
        self._max_x = screen_w - 1.0
        self._max_y = screen_h - 1.0
        assisted = config.mode == "assisted"
        self.stabilizer = GazeStabilizer(
            radius=config.assist_radius_px if assisted else config.fixation_radius_px,
            window=config.assist_window if assisted else GazeStabilizer.FIXATION_WINDOW)
        self.filter = OneEuroFilter2D(freq=30.0, mincutoff=config.filter_mincutoff,
                                      beta=config.filter_beta, dcutoff=config.filter_dcutoff)
        self.nudge = HeadNudge(
            gain_px=config.head_gain_px,
            max_offset_px=config.steer_max_px if config.mode == "steer" else config.head_max_px)
        self.target_lock = TargetLock(radius=config.snap_radius_px)
        self._last = None
        self._reset_steer()

    def _reset_steer(self):
        self._recent: deque[tuple[float, float, float]] = deque()
        self._fine_anchor: tuple[float, float] | None = None
        self._fine_id = 0
        self._fine_offset = (0.0, 0.0)
        self._exit_since: float | None = None
        self._apex_history: deque[tuple[float, float, float]] = deque()
        self._head_locked = False

    def reset(self):
        self.stabilizer.reset()
        self.filter.reset()
        self.nudge.reset()
        self.target_lock.reset()
        self._last = None
        self._reset_steer()

    def reset_fixation(self):
        """Start a fresh fixation, e.g. after the eyes re-settle from a blink."""
        self.stabilizer.reset()
        self.nudge.reset()
        if self._fine_anchor is not None:
            # Keep the steered point (a wink must click where the user aimed)
            # and re-reference the head from here.
            ax, ay = self._fine_anchor
            self._fine_anchor = self._clip(ax + self._fine_offset[0], ay + self._fine_offset[1])
            self._fine_offset = (0.0, 0.0)
            self._fine_id += 1
            self._apex_history.clear()
            self._head_locked = False

    def set_edge_sensitivity(self, level: str):
        self.config = replace(self.config, edge_sensitivity=level)

    def _clip(self, x: float, y: float) -> tuple[float, float]:
        return min(max(x, 0.0), self._max_x), min(max(y, 0.0), self._max_y)

    def update(self, estimate, reading, targets=(), now: float = 0.0) -> NavigationStep:
        """Map one new ``GazeEstimate`` (and its ``GazeReading``) to a cursor point."""
        config = self.config
        mode = config.mode
        stamp = reading.captured_at
        if mode == "legacy":
            x, y = self._clip(estimate.x, estimate.y)
        else:
            x, y = self._clip(estimate.raw_x, estimate.raw_y)
        if mode == "raw":
            return NavigationStep(x, y)
        if mode != "legacy":
            x, y = self.filter(x, y, timestamp=stamp)
        x = apply_edge_reach(x, self._max_x, config.edge_sensitivity)
        if mode == "steer":
            return self._snap_fine_aim(self._steer(x, y, reading, stamp), targets, now)

        eye_difference = (reading.features[2], reading.features[3])
        if mode == "legacy" or (mode == "assisted" and config.assist_enabled):
            x, y = self.stabilizer.update(x, y, stamp, eye_difference=eye_difference)
        elif mode == "head":
            # Only its gaze-jump counter is used: it re-references the head.
            self.stabilizer.update(x, y, stamp, eye_difference=eye_difference)

        head_offset = 0.0
        if config.uses_head:
            apex = (reading.eye_line or {}).get("nose_apex")
            dx, dy = self.nudge.update(apex, self.stabilizer.anchor_id, stamp)
            x, y = self._clip(x + dx, y + dy)
            head_offset = math.hypot(dx, dy)

        target = None
        if config.uses_targets:
            x, y, target = self.target_lock.snap(x, y, targets, now)

        if self._last is not None and math.dist((x, y), self._last) < config.deadzone_px:
            x, y = self._last
        else:
            self._last = (x, y)
        return NavigationStep(x, y, target, head_offset)

    def _snap_fine_aim(self, step: NavigationStep, targets, now: float) -> NavigationStep:
        if not self.config.uses_targets:
            return step
        if not step.fine:
            self.target_lock.reset()
            return step
        x, y, target = self.target_lock.snap(step.x, step.y, targets, now)
        return replace(step, x=x, y=y, target=target)

    def _steer(self, x: float, y: float, reading, stamp: float) -> NavigationStep:
        """``x, y``: filtered gaze in screen px for the frame captured at ``stamp``."""
        config = self.config
        recent = self._recent
        recent.append((stamp, x, y))
        horizon = max(config.steer_settle_s, config.steer_exit_s) + 0.1
        while recent and stamp - recent[0][0] > horizon:
            recent.popleft()

        if self._fine_anchor is not None:
            ax, ay = self._fine_anchor
            # After a gap in frames there is no earlier sample; compare with the
            # frozen point instead.
            earlier = next((p[1:] for p in recent
                            if p[0] < stamp and stamp - p[0] <= config.steer_exit_s), (ax, ay))
            far = math.dist((x, y), (ax, ay)) > config.steer_exit_radius_px
            fast = math.dist((x, y), earlier) > 0.75 * config.steer_exit_radius_px
            # A jump must start fast; while it is confirmed it only needs to stay far.
            jumped = far and (fast or self._exit_since is not None)
            if not jumped:
                self._exit_since = None
            elif self._exit_since is None:
                self._exit_since = stamp
            if self._exit_since is None or stamp - self._exit_since < config.steer_exit_hold_s:
                apex = (reading.eye_line or {}).get("nose_apex")
                dx, dy = self._head_offset(apex, stamp)
                self._fine_offset = (dx, dy)
                cx, cy = self._clip(ax + dx, ay + dy)
                return self._settle_output(cx, cy, math.hypot(dx, dy), fine=True)
            self._fine_anchor = None
            self._fine_offset = (0.0, 0.0)
            self._exit_since = None
            recent.clear()
            recent.append((stamp, x, y))

        window = [p for p in recent if stamp - p[0] <= config.steer_settle_s]
        if window and stamp - window[0][0] >= 0.9 * config.steer_settle_s:
            mx = sum(p[1] for p in window) / len(window)
            my = sum(p[2] for p in window) / len(window)
            inside = sum(math.dist(p[1:], (mx, my)) <= config.steer_settle_radius_px for p in window)
            if inside >= config.steer_settle_share * len(window):
                self._fine_anchor = (mx, my)
                self._fine_id += 1
                self._fine_offset = (0.0, 0.0)
                self._apex_history.clear()
                self._head_locked = False
                return self._settle_output(mx, my, 0.0, fine=True)
        return self._settle_output(x, y, 0.0, fine=False)

    def _head_offset(self, apex, stamp: float) -> tuple[float, float]:
        """Head steering offset (px); zero until the head has come to rest."""
        if apex is None:
            return self._fine_offset
        if not self._head_locked:
            history = self._apex_history
            history.append((stamp, float(apex[0]), float(apex[1])))
            while history and stamp - history[0][0] > self.config.steer_head_still_s:
                history.popleft()
            if stamp - history[0][0] < 0.9 * self.config.steer_head_still_s:
                return 0.0, 0.0
            mx = sum(p[1] for p in history) / len(history)
            my = sum(p[2] for p in history) / len(history)
            if any(math.dist(p[1:], (mx, my)) > self.config.steer_head_still for p in history):
                return 0.0, 0.0
            self._head_locked = True
            # A new id makes the nudge take this apex as its reference.
            self._fine_id += 1
        return self.nudge.update(apex, self._fine_id, stamp)

    def _settle_output(self, x: float, y: float, head_offset: float, fine: bool) -> NavigationStep:
        if self._last is not None and math.dist((x, y), self._last) < self.config.deadzone_px:
            x, y = self._last
        else:
            self._last = (x, y)
        return NavigationStep(x, y, None, head_offset, fine)
