r"""Which mapping generalizes best from a 13-point calibration? (offline, recordings only)

Run from server\ with the venv Python, on recordings from benchmark_gaze.py:

    python scripts\simulate_calibration.py s1.jsonl s2.jsonl s3.jsonl s4.jsonl s5.jsonl

A real calibration fits on 13 dots (collector.CALIBRATION_POINTS) for about one
second each, then has to work everywhere else. compare_estimators.py trains on
23 of 24 targets, which hides how a mapping behaves between and beyond so few
dots. Here every estimator is trained like a calibration:

  calibration  the recording's targets nearest the 13 calibration points,
               first --dot-frames settled frames of each (~1 s at 30 fps)
  held-out     the same recording's other targets (between and around the dots)
  next session every target of each OTHER recording (a later sitting)
  +recentre    next session after the production 5-dot re-centre

With --layout all24 the same is done with all 24 targets as calibration dots
(held-out is then empty), to see what more dots would buy. Errors are per target
(median prediction vs goal centre); each row pools every recording as the
calibration session.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from compare_estimators import (  # noqa: E402
    _offsets,
    _recentre_goals,
    _rows_for,
    estimators,
    first_frames,
    load,
)
from app.core.calibration.collector import CALIBRATION_POINTS  # noqa: E402
from app.core.calibration.recenter import fit_correction  # noqa: E402

DOT_FRAMES = 28  # COLLECT_MS 950 ms at ~30 fps


def calibration_goals(goals, screen, layout: str):
    """The recording's targets standing in for the calibration dots."""
    goals = sorted(set(goals))
    if layout == "all24":
        return goals
    sw, sh = screen
    points = CALIBRATION_POINTS if layout == "13" else [
        (x, y) for y in (0.04, 0.5, 0.96) for x in (0.04, 0.5, 0.96)]
    picked = []
    for px, py in points:
        goal = min(goals, key=lambda g: (g[0] / sw - px) ** 2 + (g[1] / sh - py) ** 2)
        if goal not in picked:
            picked.append(goal)
    return picked


def _errors(offsets):
    return [float(np.hypot(*o)) for o in offsets]


def _recentred(prediction, rows, screen):
    sw, sh = screen
    goals = [tuple(g) for g, _ in rows]
    dots = _recentre_goals(sorted(set(goals)), screen)
    pairs = [(tuple(np.median(prediction[[g == d for g in goals]], axis=0) / (sw, sh)),
              (d[0] / sw, d[1] / sh)) for d in dots]
    try:
        correction, _ = fit_correction(pairs)
    except ValueError:
        return _offsets(prediction, rows, exclude=dots)
    corrected = np.array([correction.apply(x / sw, y / sh) for x, y in prediction]) * (sw, sh)
    return _offsets(corrected, rows, exclude=dots)


def evaluate(sessions, make, layout: str, dot_frames: int):
    pools = {"calibration": [], "held-out": [], "next session": [], "+recentre": []}
    for name, train in sessions.items():
        estimator = make(train)
        rows = _rows_for(estimator, train["rows"])
        if not rows:
            raise ValueError("no frames for this source")
        dots = calibration_goals([tuple(g) for g, _ in rows], train["screen"], layout)
        fit_rows = first_frames([r for r in rows if tuple(r[0]) in dots], dot_frames)
        estimator.fit(fit_rows)
        pools["calibration"] += _errors(_offsets(estimator.predict(fit_rows), fit_rows))
        held = [r for r in rows if tuple(r[0]) not in dots]
        if held:
            pools["held-out"] += _errors(_offsets(estimator.predict(held), held))
        for other_name, other in sessions.items():
            if other_name == name:
                continue
            test = _rows_for(estimator, other["rows"])
            if not test:
                continue
            prediction = estimator.predict(test)
            pools["next session"] += _errors(_offsets(prediction, test))
            pools["+recentre"] += _errors(_recentred(prediction, test, other["screen"]))
    return pools


def fmt(errors) -> str:
    if not errors:
        return f"{'-':>15}"
    e = np.array(errors)
    return f"{np.median(e):5.0f} ({np.mean(e <= 100):4.0%})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sessions", type=Path, nargs="+")
    parser.add_argument("--layout", choices=("13", "9", "all24"), default="13")
    parser.add_argument("--dot-frames", type=int, default=DOT_FRAMES)
    parser.add_argument("--only", help="run only estimators whose label contains this text")
    args = parser.parse_args()
    sessions = {p.stem: load(p) for p in args.sessions}
    print(f"layout {args.layout}, {args.dot_frames} frames per dot; median px per target "
          "(share within 100 px), pooled over every recording as the calibration session")
    cols = ("calibration", "held-out", "next session", "+recentre")
    print(f"{'estimator':<48}" + "".join(f"{c:>16}" for c in cols))
    for label, make in estimators().items():
        if args.only and args.only not in label:
            continue
        try:
            pools = evaluate(sessions, make, args.layout, args.dot_frames)
        except (ValueError, np.linalg.LinAlgError) as exc:
            print(f"{label[:47]:<48} not available ({exc})")
            continue
        print(f"{label[:47]:<48}" + "".join(f"{fmt(pools[c]):>16}" for c in cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
