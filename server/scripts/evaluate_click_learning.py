r"""Offline proof for "learn from every click" (app/workers/click_learning.py).

Run from server\ with the venv Python, on recordings from benchmark_gaze.py:

    python scripts\evaluate_click_learning.py s1.jsonl s2.jsonl s3.jsonl [--snap-px 140]

Each recording is replayed once through the raw gaze mapping (no correction),
then scored twice on the same frames:

  fixed     the correction stays as recorded (the saved re-centre, if any)
  learning  after every trial the goal button counts as one snapped click, and
            ClickLearner updates the correction used for the NEXT trials

Only clicks a real user could make count: the corrected gaze must be within
--snap-px of the goal (the worker's snapping radius). Errors are per target
(median settled cursor vs goal centre), so later trials show whether learning
removed drift. Nothing is learned from the trial it is scored on.
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.gaze.evaluation import SETTLE_S, CursorSample, accuracy_summary, per_target  # noqa: E402
from app.core.gaze.screen_mapper import ScreenCorrection  # noqa: E402
from app.workers.click_learning import ClickLearner  # noqa: E402

DEFAULT_SNAP_PX = 140.0


def apply_correction(samples, correction, screen):
    """Raw (uncorrected) cursor samples in px -> the same samples with a correction."""
    if correction is None:
        return list(samples)
    w, h = screen
    out = []
    for s in samples:
        x, y = correction.apply(s.x / w, s.y / h)
        out.append(CursorSample(s.t, x * w, y * h))
    return out


def settled_point(samples, trial):
    settled = [(s.x, s.y) for s in samples if trial.onset + SETTLE_S <= s.t < trial.end]
    return tuple(np.median(np.array(settled), axis=0)) if len(settled) >= 3 else None


def evaluate(raw_samples, trials, screen, start_correction=None, learner=None,
             snap_px: float = DEFAULT_SNAP_PX):
    """Corrected samples for every trial, learning (if ``learner``) only from earlier trials."""
    current = start_correction
    corrected, clicks = [], 0
    for trial in trials:
        in_trial = [s for s in raw_samples if trial.onset <= s.t < trial.end]
        shown = apply_correction(in_trial, current, screen)
        corrected += shown
        if learner is None:
            continue
        gaze = settled_point(shown, trial)
        if gaze is None:
            continue
        gx, gy = trial.goal.center
        if math.hypot(gaze[0] - gx, gaze[1] - gy) > snap_px:
            continue  # the cursor would not have snapped: no click to learn from
        clicks += 1
        updated = learner.observe_click(gaze, trial.goal, screen, current)
        if updated is not None:
            current = updated
    return corrected, clicks, current


def halves(results):
    mid = len(results) // 2
    early = [r.error for r in results[:mid]]
    late = [r.error for r in results[mid:]]
    return (float(np.median(early)) if early else math.nan, float(np.median(late)) if late else math.nan)


def compare(raw_samples, trials, screen, start_correction=None, snap_px: float = DEFAULT_SNAP_PX):
    fixed, _, _ = evaluate(raw_samples, trials, screen, start_correction)
    learner = ClickLearner(enabled=True)
    learned, clicks, final = evaluate(raw_samples, trials, screen, start_correction, learner, snap_px)
    rows = {}
    for name, samples in (("fixed", fixed), ("learning", learned)):
        results = per_target(samples, trials)
        summary = accuracy_summary(results, screen[1])
        early, late = halves(results)
        rows[name] = {**summary, "error_px_p50_first_half": early, "error_px_p50_second_half": late}
    rows["learning"]["clicks_used"] = clicks
    rows["learning"]["updates"] = learner.updates
    return rows


def _load(path: Path, profile_id: str | None):
    from benchmark_gaze import load_session, replay_mode
    from app.config import get_settings
    from app.core.calibration.profile import load_profile
    from app.core.gaze.navigation import NavigationConfig
    settings = get_settings()
    meta, trials, readings, _ = load_session(path)
    _, model = load_profile(settings.profiles_dir, profile_id or meta.get("profile_id"))
    if model is None:
        raise SystemExit(f"{path}: its calibration profile {meta.get('profile_id')} is missing.")
    model.set_correction(None)
    screen = tuple(meta["screen"])
    raw, _ = replay_mode(NavigationConfig(mode="raw"), model, readings, trials, screen,
                         settings.cursor_smoothing)
    start = ScreenCorrection(meta["recenter"]) if meta.get("recenter") else None
    return raw, trials, screen, start


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--profile-id")
    parser.add_argument("--snap-px", type=float, default=DEFAULT_SNAP_PX)
    args = parser.parse_args()
    keys = ("targets", "error_px_p50", "error_px_p95", "reach_rate",
            "error_px_p50_first_half", "error_px_p50_second_half")
    for path in args.recordings:
        raw, trials, screen, start = _load(path, args.profile_id)
        rows = compare(raw, trials, screen, start, args.snap_px)
        print(f"\n{path.name}  (screen {screen[0]}x{screen[1]}, recorded re-centre: {start is not None})")
        print("  " + " ".join(f"{k:>24}" for k in ("mode",) + keys))
        for name, row in rows.items():
            values = [f"{row.get(k, math.nan):24.2f}" if isinstance(row.get(k), float) else f"{row.get(k, '-'):>24}"
                      for k in keys]
            print("  " + f"{name:>24} " + " ".join(values))
        print(f"  clicks used: {rows['learning']['clicks_used']}, corrections: {rows['learning']['updates']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
