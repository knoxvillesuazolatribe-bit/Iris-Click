"""Camera-timed gaze processing shared by calibration and the tracking worker.

No GUI, camera or OS input dependencies. Predictions stay unclipped here; the
worker clips them to the screen.
"""

import math
import time
from dataclasses import dataclass

from app.core.gaze.feature_sources import (
    features_for_model,
    model_feature_source,
    reference_source,
)
from app.core.gaze.smoothing import OneEuroFilter2D

MIN_OPEN_EAR = 0.10
MAX_SAMPLE_AGE_S = 0.25
POST_BLINK_SETTLE_S = 0.10
FEATURE_SMOOTHING_ALPHA = 0.6
FEATURE_REFERENCE_PERIOD_S = 0.020
# Fitted pupils drop out on ~20% of frames when looking at the bottom row
# (s3.jsonl), mostly for 1-3 frames; shorter gaps reuse the last pupil frame.
FALLBACK_HOLD_S = 0.2
# The fallback model sat ~220 px below the pupil model on the same frames
# (s3.jsonl); this EMA of their difference keeps a switch from jumping.
FALLBACK_OFFSET_ALPHA = 0.1

# Reasons that mean "no new usable estimate yet", not "tracking was lost".
TRANSIENT_REASONS = (None, "duplicate", "eyes_closed", "recovering")


class ReadingGate:
    """Accept each fresh camera observation at most once, per consumer.

    ``captured_at`` and ``now`` share the perf_counter clock. EAR is a
    conservative visibility check, not a landmark confidence score.
    """

    def __init__(self, min_open_ear=MIN_OPEN_EAR, max_age=MAX_SAMPLE_AGE_S,
                 recovery=POST_BLINK_SETTLE_S):
        self.min_open_ear = min_open_ear
        self.max_age = max_age
        self.recovery = recovery
        self.reset()

    def reset(self):
        self.last_timestamp = None
        self.resume_at = 0.0
        self.reason = None

    def accept(self, reading, now=None):
        now = time.perf_counter() if now is None else now
        stamp = reading.captured_at
        if not math.isfinite(stamp) or stamp <= 0 or not math.isfinite(now) or stamp > now:
            self.reason = "invalid_timestamp"
        elif now - stamp > self.max_age:
            self.reason = "stale"
        elif self.last_timestamp is not None and stamp <= self.last_timestamp:
            self.reason = "duplicate"
        else:
            self.last_timestamp = stamp
            if not reading.face_found:
                self.reason = "no_face"
            elif (len(reading.features) != 6
                  or not all(math.isfinite(v) for v in reading.features)):
                self.reason = "invalid_features"
            elif not all(math.isfinite(v) for v in (reading.left_ear, reading.right_ear)):
                self.reason = "invalid_eyes"
            elif min(reading.left_ear, reading.right_ear) < self.min_open_ear:
                self.resume_at = stamp + self.recovery
                self.reason = "eyes_closed"
            elif stamp < self.resume_at:
                self.reason = "recovering"
            else:
                self.reason = None
        return self.reason is None


@dataclass(frozen=True)
class GazeEstimate:
    raw_x: float
    raw_y: float
    x: float
    y: float


class GazePipeline:
    """Time-aware feature EMA -> calibrated mapping -> One Euro filter.

    ``None`` means there is no new usable estimate; ``reason`` says why.
    """

    def __init__(self):
        self.gate = ReadingGate()
        self.cursor_filter = OneEuroFilter2D(freq=50.0, mincutoff=0.8, beta=0.005)
        self.reset()

    @property
    def reason(self):
        return self.gate.reason

    def reset(self):
        self.gate.reset()
        self._reset_signal()
        self._feature_source = None
        self.using_reference_model = False
        self._primary_hold = None
        # Primary minus fallback prediction (screen fractions), learned on
        # frames where both sources exist.
        self._fallback_offset = None

    def _learn_fallback_offset(self, model, features, reference, reference_features):
        try:
            px, py = model.predict(features)
            rx, ry = reference.predict(reference_features)
        except (ValueError, TypeError, OverflowError, FloatingPointError):
            return
        dx, dy = px - rx, py - ry
        if not (math.isfinite(dx) and math.isfinite(dy)):
            return
        if self._fallback_offset is None:
            self._fallback_offset = (dx, dy)
        else:
            ox, oy = self._fallback_offset
            a = FALLBACK_OFFSET_ALPHA
            self._fallback_offset = (ox + a * (dx - ox), oy + a * (dy - oy))

    def _reset_signal(self):
        self.cursor_filter.reset()
        self._features = None
        self._last_signal_time = None

    def process(self, reading, model, smoothing=0.25, output_size=None, now=None):
        if not self.gate.accept(reading, now=now):
            if self.reason not in ("duplicate", "eyes_closed", "recovering"):
                self._reset_signal()
            return None

        stamp = reading.captured_at
        if (self._last_signal_time is not None
                and stamp - self._last_signal_time > MAX_SAMPLE_AGE_S):
            self._reset_signal()

        effective_model = model
        source = model_feature_source(model)
        features = features_for_model(reading, model)
        self.using_reference_model = False
        reference = (getattr(model, "reference_model", None)
                     if reference_source(source) is not None else None)
        reference_features = (features_for_model(reading, reference)
                              if reference is not None else None)
        if features is not None:
            self._primary_hold = (features, stamp)
            if reference_features is not None:
                self._learn_fallback_offset(model, features, reference, reference_features)
        elif (self._primary_hold is not None
              and stamp - self._primary_hold[1] <= FALLBACK_HOLD_S):
            # A brief dropout (often a lowered lid when looking down): keep
            # the primary model on its last features instead of switching.
            features = self._primary_hold[0]
        offset = (0.0, 0.0)
        if features is None and reference_features is not None:
            effective_model = reference
            source = reference_source(source)
            features = reference_features
            offset = self._fallback_offset or (0.0, 0.0)
            self.using_reference_model = True
        if self._feature_source is not None and self._feature_source != source:
            # Feature vectors of two sources never blend. The screen-space
            # filter may continue only when the fallback is aligned to the
            # primary; otherwise the cursor would jump by the models' bias.
            if self._fallback_offset is None:
                self._reset_signal()
            else:
                self._features = None
        self._feature_source = source
        if features is None:
            self.gate.reason = "missing_features"
            self._reset_signal()
            return None
        if self._features is None:
            self._features = tuple(features)
        else:
            dt = stamp - self._last_signal_time
            alpha = 1.0 - (1.0 - FEATURE_SMOOTHING_ALPHA) ** (dt / FEATURE_REFERENCE_PERIOD_S)
            self._features = tuple(alpha * r + (1.0 - alpha) * p
                                   for r, p in zip(features, self._features))
        self._last_signal_time = stamp

        def predict(values):
            x, y = effective_model.predict(values)
            x, y = x + offset[0], y + offset[1]
            if output_size is not None:
                return x * float(output_size[0]), y * float(output_size[1])
            return x, y

        try:
            raw_x, raw_y = predict(features)
            sx, sy = predict(self._features)
        except (ValueError, TypeError, OverflowError, FloatingPointError):
            raw_x = raw_y = sx = sy = math.nan
        if not all(math.isfinite(v) for v in (raw_x, raw_y, sx, sy)):
            self.gate.reason = "invalid_prediction"
            self._reset_signal()
            return None
        self.cursor_filter.set_mincutoff(0.2 + (1.0 - smoothing) * 0.8)
        x, y = self.cursor_filter(sx, sy, timestamp=stamp)
        return GazeEstimate(raw_x, raw_y, x, y)
