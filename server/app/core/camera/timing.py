"""Frame-delivery statistics: regularity, stalls, bursts and relative age.

Input is the camera delivery log, (read-return perf_counter seconds, driver
timestamp ms or None) per frame. With driver timestamps the extra delay of
each frame over the least-delayed one is measurable: driver and host clocks
differ by an unknown constant, so only this *relative* age is observable, not
sensor-to-host latency.
"""

import math

import numpy as np

from app.core.gaze.diagnostics import summarize

# An interval this many nominal periods long is a stall; this short, a burst
# (the frame was queued behind its predecessor).
STALL_PERIODS = 2.0
BURST_PERIODS = 0.5
# Crystal clocks agree within ~0.01%; 2% apart means the driver timestamp is
# not a real clock.
DRIVER_CLOCK_TOLERANCE = 0.02


def delivery_report(deliveries, nominal_fps: float = 30.0) -> dict:
    times = [t for t, _ in deliveries]
    if len(times) < 3:
        return {"frames": len(times)}
    period_ms = 1000.0 / nominal_fps
    intervals = [(b - a) * 1000.0 for a, b in zip(times, times[1:])]
    span_s = times[-1] - times[0]
    report = {
        "frames": len(times),
        "fps": round((len(times) - 1) / span_s, 1),
        "interval_ms": summarize(intervals),
        "stall_rate": round(sum(i > STALL_PERIODS * period_ms for i in intervals)
                            / len(intervals), 3),
        "burst_rate": round(sum(i < BURST_PERIODS * period_ms for i in intervals)
                            / len(intervals), 3),
    }
    stamped = [(t, ms) for t, ms in deliveries if ms is not None and math.isfinite(ms)]
    # Driver clocks that never advance (some DirectShow drivers) carry no timing.
    if len(stamped) < 3 or stamped[-1][1] <= stamped[0][1]:
        return report
    t0, ms0 = stamped[0]
    driver = [b[1] - a[1] for a, b in zip(stamped, stamped[1:])]
    report["driver_interval_ms"] = summarize(driver)
    # Slope over all frames: endpoint ratios are skewed by batched delivery.
    ratio = float(np.polyfit([(t - t0) * 1000.0 for t, _ in stamped],
                             [ms - ms0 for _, ms in stamped], 1)[0])
    report["driver_clock_ratio"] = round(ratio, 3)
    # Some drivers stamp frame_count / nominal_fps instead of real exposure
    # time; such a clock runs at the wrong rate and its "age" is meaningless.
    if abs(ratio - 1.0) <= DRIVER_CLOCK_TOLERANCE:
        offsets = [(t - t0) * 1000.0 - (ms - ms0) for t, ms in stamped]
        floor = min(offsets)
        report["relative_age_ms"] = summarize([o - floor for o in offsets])
    return report
