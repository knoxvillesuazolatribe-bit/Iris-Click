"""Low-overhead latency and throughput metrics for the gaze pipeline.

Hot-path cost is a ``deque.append`` per value; percentiles are computed only
when a summary window closes. All durations are milliseconds and all clocks
are ``time.perf_counter`` unless a caller says otherwise.

``captured_at`` is stamped when ``VideoCapture.read`` returns, so every
"age" metric excludes sensor exposure and driver buffering.
"""

import json
import logging
import math
from collections import Counter, deque
from pathlib import Path

WINDOW_SAMPLES = 2048


def percentile(sorted_values, fraction: float) -> float:
    """Linear-interpolated percentile of an already sorted sequence."""
    if not sorted_values:
        return math.nan
    position = (len(sorted_values) - 1) * fraction
    low = math.floor(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def summarize(values) -> dict:
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "p50": round(percentile(ordered, 0.50), 2),
        "p95": round(percentile(ordered, 0.95), 2),
        "max": round(ordered[-1], 2) if ordered else math.nan,
    }


class Diagnostics:
    """Windowed metric summaries plus an optional per-frame JSONL trace.

    Disabled instances accept every call and do nothing, so callers never
    branch on ``enabled``.
    """

    def __init__(self, enabled: bool = False, interval_s: float = 10.0,
                 trace_path: Path | None = None, logger: logging.Logger | None = None):
        self.enabled = enabled
        self.interval_s = interval_s
        self._logger = logger or logging.getLogger("irisclick.diagnostics")
        self._values: dict[str, deque] = {}
        self._counts: Counter = Counter()
        self._window_start: float | None = None
        self._trace = None
        if enabled and trace_path is not None:
            Path(trace_path).parent.mkdir(parents=True, exist_ok=True)
            self._trace = open(trace_path, "a", encoding="utf-8", buffering=1 << 16)

    def record(self, name: str, value: float):
        if not self.enabled or value is None or not math.isfinite(value):
            return
        values = self._values.get(name)
        if values is None:
            values = self._values[name] = deque(maxlen=WINDOW_SAMPLES)
        values.append(value)

    def record_many(self, values: dict | None, prefix: str = ""):
        if not self.enabled or not values:
            return
        for name, value in values.items():
            self.record(prefix + name, value)

    def count(self, name: str, n: int = 1):
        if self.enabled:
            self._counts[name] += n

    def trace(self, row: dict):
        if self._trace is not None:
            self._trace.write(json.dumps(row, separators=(",", ":")) + "\n")

    def maybe_report(self, now: float) -> dict | None:
        """Log and return the window summary once ``interval_s`` has passed."""
        if not self.enabled:
            return None
        if self._window_start is None:
            self._window_start = now
            return None
        elapsed = now - self._window_start
        if elapsed < self.interval_s:
            return None
        report = {
            "window_s": round(elapsed, 2),
            "stages_ms": {name: summarize(v) for name, v in sorted(self._values.items()) if v},
            "counts": dict(self._counts),
            "rates_hz": {name: round(n / elapsed, 2) for name, n in self._counts.items()},
        }
        self._logger.info("gaze diagnostics %s", json.dumps(report, separators=(",", ":")))
        self._values.clear()
        self._counts.clear()
        self._window_start = now
        if self._trace is not None:
            self._trace.flush()
        return report

    def close(self):
        if self._trace is not None:
            self._trace.close()
            self._trace = None
