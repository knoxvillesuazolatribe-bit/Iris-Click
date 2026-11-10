r"""One Euro (production) vs Kalman smoothing on the same recorded gaze.

Run from server\ with the venv Python, on recordings from benchmark_gaze.py:

    python scripts\compare_filters.py s1.jsonl s2.jsonl

The raw gaze (no smoothing) of each recording is replayed once, then smoothed
by: no filter, the One Euro filter with the production settings
(GAZE_FILTER_MINCUTOFF / GAZE_FILTER_BETA), and a constant-velocity Kalman
filter at a few noise settings. Every variant is scored with the benchmark's
own score_session: settled error, jitter, how often the goal is acquired and
how fast, and how often a wink would hit a neighbouring button.

Offline only: production keeps the One Euro filter unless this shows a clear win.
A Kalman filter cut webcam gaze error from 2.71 to 1.33 degrees in one study
(arXiv 1907.04325); the One Euro filter is Casiez, Roussel & Vogel (CHI 2012).
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.gaze.evaluation import CursorSample, score_session  # noqa: E402
from app.core.gaze.smoothing import OneEuroFilter2D  # noqa: E402

KALMAN_SETTINGS = ((50.0, 900.0), (200.0, 900.0), (800.0, 900.0), (200.0, 3600.0))
GAP_RESET_S = 0.3


class KalmanFilter2D:
    """Constant-velocity Kalman filter per axis (state: position, velocity), in px.

    ``process_noise``: how fast the velocity may change (px/s^2 spectral density);
    ``measurement_noise``: variance of one gaze sample (px^2).
    """

    def __init__(self, process_noise: float, measurement_noise: float):
        self.q, self.r = float(process_noise), float(measurement_noise)
        self.reset()

    def reset(self):
        self.state = None
        self.cov = None
        self.t = None

    def __call__(self, x: float, y: float, timestamp: float):
        z = np.array([x, y], dtype=float)
        if self.state is None or self.t is None or timestamp - self.t > GAP_RESET_S:
            self.state = np.array([x, y, 0.0, 0.0])
            self.cov = np.diag([self.r, self.r, 1e5, 1e5])
            self.t = timestamp
            return x, y
        dt = max(1e-3, timestamp - self.t)
        self.t = timestamp
        f = np.eye(4)
        f[0, 2] = f[1, 3] = dt
        g = np.array([[dt ** 3 / 3, dt ** 2 / 2], [dt ** 2 / 2, dt]]) * self.q
        q = np.zeros((4, 4))
        q[np.ix_([0, 2], [0, 2])] = g
        q[np.ix_([1, 3], [1, 3])] = g
        self.state = f @ self.state
        self.cov = f @ self.cov @ f.T + q
        h = np.zeros((2, 4))
        h[0, 0] = h[1, 1] = 1.0
        s = h @ self.cov @ h.T + np.eye(2) * self.r
        k = self.cov @ h.T @ np.linalg.inv(s)
        self.state = self.state + k @ (z - h @ self.state)
        self.cov = (np.eye(4) - k @ h) @ self.cov
        return float(self.state[0]), float(self.state[1])


def smooth(samples, make_filter):
    """Applies a fresh filter to time-ordered samples (``make_filter`` None: unchanged)."""
    if make_filter is None:
        return list(samples)
    flt, out = make_filter(), []
    for s in samples:
        x, y = flt(s.x, s.y, s.t) if not isinstance(flt, OneEuroFilter2D) else flt(s.x, s.y, timestamp=s.t)
        out.append(CursorSample(s.t, x, y))
    return out


def variants(mincutoff: float, beta: float):
    yield "none", None
    yield f"one-euro {mincutoff}/{beta}", lambda: OneEuroFilter2D(mincutoff=mincutoff, beta=beta)
    for q, r in KALMAN_SETTINGS:
        yield f"kalman q{q:g} r{r:g}", (lambda q=q, r=r: KalmanFilter2D(q, r))


def compare(raw_samples, trials, mincutoff: float, beta: float) -> dict:
    return {name: score_session(smooth(raw_samples, make), trials) for name, make in variants(mincutoff, beta)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--profile-id")
    args = parser.parse_args()
    from evaluate_click_learning import _load
    from app.config import get_settings
    settings = get_settings()
    keys = ("error_px_p50", "error_px_p95", "jitter_px_rms", "acquired_rate", "acquire_ms_p50",
            "wrong_target_rate")
    for path in args.recordings:
        raw, trials, screen, start = _load(path, args.profile_id)
        if start is not None:
            from evaluate_click_learning import apply_correction
            raw = apply_correction(raw, start, screen)
        rows = compare(raw, trials, settings.gaze_filter_mincutoff, settings.gaze_filter_beta)
        print(f"\n{path.name}")
        print("  " + f"{'filter':>22} " + " ".join(f"{k:>18}" for k in keys))
        for name, row in rows.items():
            print("  " + f"{name:>22} " + " ".join(
                f"{row.get(k, math.nan):18.3f}" for k in keys))
    return 0


if __name__ == "__main__":
    sys.exit(main())
