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
        fallback_source = reference_source(source)
        if features is None and fallback_source is not None:
            reference = getattr(model, "reference_model", None)
            if reference is not None:
                reference_features = features_for_model(reading, reference)
                if reference_features is not None:
                    effective_model = reference
                    source = fallback_source
                    features = reference_features
                    self.using_reference_model = True
        if self._feature_source is not None and self._feature_source != source:
            # Never blend two coordinate systems during a source transition.
            self._reset_signal()
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
            if output_size is not None:
                return effective_model.predict_for_screen(values, *output_size)
            return effective_model.predict(values)

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
