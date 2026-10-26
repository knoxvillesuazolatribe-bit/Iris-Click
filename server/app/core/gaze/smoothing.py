"""Cursor smoothing: One Euro filter, inter-frame glide and fixation lock."""

import math


class _LowPassFilter:
    def __init__(self, alpha):
        self._alpha = alpha
        self._y = None
        self._s = None

    def set_alpha(self, alpha):
        self._alpha = alpha

    def filter(self, value):
        s = value if self._y is None else self._alpha * value + (1.0 - self._alpha) * self._s
        self._y = value
        self._s = s
        return s

    def last_filtered_value(self):
        return self._s


class OneEuroFilter:
    """Adaptive low-pass filter (Casiez, Roussel & Vogel, CHI 2012).

    Smooths aggressively while the signal is nearly still (killing landmark
    jitter) and relaxes during fast intentional eye movement.
    """

    def __init__(self, freq=50.0, mincutoff=0.5, beta=0.005, dcutoff=1.0):
        if (not all(math.isfinite(v) for v in (freq, mincutoff, beta, dcutoff))
                or min(freq, mincutoff, dcutoff) <= 0 or beta < 0):
            raise ValueError("Filter frequencies must be positive and beta non-negative.")
        self._initial_freq = freq
        self.freq = freq
        self.mincutoff = mincutoff
        self.beta = beta
        self.dcutoff = dcutoff
        self._x_filter = _LowPassFilter(self._alpha(mincutoff))
        self._dx_filter = _LowPassFilter(self._alpha(dcutoff))
        self._last_time = None

    def _alpha(self, cutoff):
        te = 1.0 / self.freq
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / te)

    def __call__(self, x, timestamp=None):
        if not math.isfinite(x) or (timestamp is not None and not math.isfinite(timestamp)):
            raise ValueError("Filter input and timestamp must be finite.")
        if timestamp is not None and self._last_time is not None:
            dt = timestamp - self._last_time
            if dt <= 0:
                return self._x_filter.last_filtered_value()
            self.freq = 1.0 / dt
        self._last_time = timestamp

        # Velocity relative to the previous FILTERED position, as in the
        # reference algorithm, so the remaining lag after a shift is kept.
        prev_x = self._x_filter.last_filtered_value()
        dx = 0.0 if prev_x is None else (x - prev_x) * self.freq
        self._dx_filter.set_alpha(self._alpha(self.dcutoff))
        edx = self._dx_filter.filter(dx)
        cutoff = self.mincutoff + self.beta * abs(edx)
        self._x_filter.set_alpha(self._alpha(cutoff))
        return self._x_filter.filter(x)

    def reset(self):
        self.freq = self._initial_freq
        self._x_filter = _LowPassFilter(self._alpha(self.mincutoff))
        self._dx_filter = _LowPassFilter(self._alpha(self.dcutoff))
        self._last_time = None


class OneEuroFilter2D:
    def __init__(self, freq=50.0, mincutoff=0.5, beta=0.005, dcutoff=1.0):
        self._fx = OneEuroFilter(freq, mincutoff, beta, dcutoff)
        self._fy = OneEuroFilter(freq, mincutoff, beta, dcutoff)

    def __call__(self, x, y, timestamp=None):
        return self._fx(x, timestamp), self._fy(y, timestamp)

    def reset(self):
        self._fx.reset()
        self._fy.reset()

    def set_mincutoff(self, value):
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Minimum cutoff must be positive and finite.")
        self._fx.mincutoff = value
        self._fy.mincutoff = value


class CursorGlide:
    """Interpolate the displayed cursor between camera frames.

    The gaze estimate changes only when a camera frame arrives (12-30 Hz) while
    the UI tick runs at ~50 Hz. Each new target is reached linearly over part
    of one measured frame interval, adding at most ``max_duration`` latency.
    """

    def __init__(self, min_duration=0.02, max_duration=0.06, interval_fraction=0.5):
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.interval_fraction = interval_fraction
        self.reset()

    def reset(self):
        self._start = None
        self._end = None
        self._start_time = 0.0
        self._duration = self.min_duration
        self._last_target_time = None

    def set_target(self, x, y, now):
        current = self.position(now) or (x, y)
        if self._last_target_time is not None:
            interval = (now - self._last_target_time) * self.interval_fraction
            self._duration = min(self.max_duration, max(self.min_duration, interval))
        self._last_target_time = now
        self._start = current
        self._end = (x, y)
        self._start_time = now

    def position(self, now):
        if self._end is None:
            return None
        t = min(1.0, max(0.0, (now - self._start_time) / self._duration))
        sx, sy = self._start
        ex, ey = self._end
        return sx + (ex - sx) * t, sy + (ey - sy) * t


class GazeStabilizer:
    """Hold the cursor still during fixations; move only on deliberate shifts.

    * Fixation lock: while samples stay within ``radius`` of the anchor, the
      cursor stays at the running mean of the fixation.
    * Deliberate shift: the anchor moves once ``confirm_frames`` consecutive
      samples (spanning ``confirm_s``) land outside the radius on the same side.
      A real eye movement sweeps one way; noise spikes point anywhere.
    * Binocular sync: a sudden jump in the left/right eye difference means the
      two eyes are no longer tracked together, so that frame is ignored.
    """

    FIXATION_WINDOW = 12
    SAME_DIRECTION_COS = math.cos(math.radians(50))

    def __init__(self, radius=80.0, confirm_s=0.06, confirm_frames=2,
                 eye_jump_limit=0.12, eye_baseline_alpha=0.2):
        self.radius = float(radius)
        self.confirm_s = confirm_s
        self.confirm_frames = confirm_frames
        self.eye_jump_limit = eye_jump_limit
        self.eye_baseline_alpha = eye_baseline_alpha
        self.reset()

    def reset(self):
        self._anchor = None
        self._fixation = []
        self._candidate = []
        self._candidate_since = None
        self._eye_baseline = None
        # Increments on every new fixation (a deliberate gaze jump).
        self.anchor_id = 0

    def _eyes_in_sync(self, eye_difference):
        if eye_difference is None:
            return True
        dx, dy = eye_difference
        if self._eye_baseline is None:
            self._eye_baseline = (dx, dy)
            return True
        bx, by = self._eye_baseline
        jump = math.hypot(dx - bx, dy - by)
        # Always follow slowly, so a real head turn is absorbed in a few frames.
        a = self.eye_baseline_alpha
        self._eye_baseline = (bx + a * (dx - bx), by + a * (dy - by))
        return jump <= self.eye_jump_limit

    def update(self, x, y, now, eye_difference=None):
        """Return the stabilised (x, y) for a new gaze sample."""
        if not self._eyes_in_sync(eye_difference):
            return self._anchor if self._anchor is not None else (x, y)
        if self._anchor is None:
            self._lock((x, y))
            return self._anchor

        ax, ay = self._anchor
        if math.hypot(x - ax, y - ay) <= self.radius:
            self._candidate = []
            self._candidate_since = None
            self._fixation.append((x, y))
            del self._fixation[:-self.FIXATION_WINDOW]
            n = len(self._fixation)
            self._anchor = (sum(p[0] for p in self._fixation) / n,
                            sum(p[1] for p in self._fixation) / n)
            return self._anchor

        if self._candidate:
            fx, fy = self._candidate[0]
            first = (fx - ax, fy - ay)
            this = (x - ax, y - ay)
            cos = ((first[0] * this[0] + first[1] * this[1])
                   / max(1e-9, math.hypot(*first) * math.hypot(*this)))
            if cos < self.SAME_DIRECTION_COS:
                self._candidate = []
                self._candidate_since = None
        if not self._candidate:
            self._candidate_since = now
        self._candidate.append((x, y))
        if (len(self._candidate) >= self.confirm_frames
                and now - self._candidate_since >= self.confirm_s):
            self._lock((x, y))
        return self._anchor

    def _lock(self, point):
        self.anchor_id += 1
        self._anchor = point
        self._fixation = [point]
        self._candidate = []
        self._candidate_since = None
