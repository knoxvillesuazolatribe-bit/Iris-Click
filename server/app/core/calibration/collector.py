"""Per-dot sample collection for the hybrid calibration.

Every accepted camera frame records the features of every candidate source,
so all sources are fitted and judged on exactly the same frames and dots.
"""

import numpy as np

from app.core.gaze.feature_sources import (
    CANDIDATE_SOURCES,
    IRIS_FEATURE_SOURCE,
    features_for_source,
)
from app.core.gaze.pipeline import ReadingGate

# 13-point calibration: centre first, then edge midpoints, corners and four
# inner points. The extra points sit where a 3x3 grid has to extrapolate,
# which is where a quadratic fit strays furthest. The outer ring is at 4%/96%
# (was 8%/92%) so browser tabs, the address bar, window close buttons and the
# taskbar lie inside the calibrated area instead of being extrapolated.
EDGE = 0.04
CALIBRATION_POINTS = [
    (0.50, 0.50),
    (0.50, EDGE), (1 - EDGE, 0.50), (0.50, 1 - EDGE), (EDGE, 0.50),
    (EDGE, EDGE), (1 - EDGE, EDGE), (1 - EDGE, 1 - EDGE), (EDGE, 1 - EDGE),
    (0.29, 0.29), (0.71, 0.29),
    (0.71, 0.71), (0.29, 0.71),
]

COLLECT_MS = 950
MAX_COLLECT_MS = 2600
MIN_SAMPLES_PER_POINT = 15
MAX_POINT_RETRIES = 2

# Samples further than this many median-absolute-deviations from the dot's
# median are dropped: blinks, saccades to the wrong spot or a bad landmark
# read would otherwise poison the point.
OUTLIER_MAD_MULTIPLIER = 3.0
MIN_SAMPLES_TO_FILTER = 6
FEATURE_MAD_FLOORS = np.array([0.004, 0.004, 0.003, 0.003, 0.01, 0.01])


def outlier_mask(feature_rows) -> list[bool]:
    if len(feature_rows) < MIN_SAMPLES_TO_FILTER:
        return [True] * len(feature_rows)
    rows = np.array(feature_rows, dtype=float)
    median = np.median(rows, axis=0)
    mad = np.maximum(np.median(np.abs(rows - median), axis=0), FEATURE_MAD_FLOORS)
    keep = np.all(np.abs(rows - median) / mad <= OUTLIER_MAD_MULTIPLIER, axis=1)
    return keep.tolist() if np.any(keep) else [True] * len(feature_rows)


class PointCollector:
    """Collects one dot; frames captured before ``started_at`` are ignored."""

    def __init__(self, target: tuple[float, float], started_at: float):
        self.target = target
        self.started_at = started_at
        self.gate = ReadingGate()
        self._rows: list[dict] = []

    @property
    def reason(self):
        return self.gate.reason

    def observe(self, reading) -> bool:
        if reading.captured_at < self.started_at or not self.gate.accept(reading):
            return False
        # The iris-ring vector exists on every face frame; it drives the
        # outlier mask applied to all sources.
        if features_for_source(reading, IRIS_FEATURE_SOURCE) is None:
            return False
        self._rows.append({source: features_for_source(reading, source)
                           for source in CANDIDATE_SOURCES})
        return True

    def cleaned_rows(self) -> list[dict]:
        keep = outlier_mask([row[IRIS_FEATURE_SOURCE] for row in self._rows])
        return [row for row, ok in zip(self._rows, keep) if ok]

    def is_finished(self, elapsed_ms: float) -> bool:
        if elapsed_ms >= MAX_COLLECT_MS:
            return True
        # Low FPS extends collection rather than repeating cached frames.
        return elapsed_ms >= COLLECT_MS and len(self.cleaned_rows()) >= MIN_SAMPLES_PER_POINT

    def has_enough(self) -> bool:
        return len(self.cleaned_rows()) >= MIN_SAMPLES_PER_POINT


class CalibrationCollector:
    """Accumulates accepted dots as per-source (features, target) rows."""

    def __init__(self):
        self.samples: dict[str, list] = {source: [] for source in CANDIDATE_SOURCES}
        # Per-source sample count at each dot; a source needs every dot covered.
        self.point_counts: dict[str, list[int]] = {source: [] for source in CANDIDATE_SOURCES}

    def add_point(self, point: PointCollector):
        rows = point.cleaned_rows()
        for source in CANDIDATE_SOURCES:
            values = [(row[source], point.target) for row in rows if row[source] is not None]
            self.samples[source].extend(values)
            self.point_counts[source].append(len(values))

    @property
    def sample_count(self) -> int:
        return len(self.samples[IRIS_FEATURE_SOURCE])
