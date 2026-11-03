r"""Controlled comparison of gaze estimators on benchmark recordings.

Run from server\ with the venv Python:

    python scripts\compare_estimators.py s2.jsonl s3.jsonl s4.jsonl s5.jsonl

Every estimator is trained and tested on the same frames (settled on the
target, eyes open) under three protocols, all on held-out targets:

  within   leave-one-goal-position-out inside one recording (fresh personal fit)
  cross    fit on all of recording A, test on recording B (calibrate once, use later)
  +recentre  cross, then the production 5-dot re-centre fitted on B's targets
           nearest the re-centre dots and scored on B's other targets

Errors are per target (median prediction vs goal centre): median px, degrees at
the recording's measured eye distance, |x| and |y| medians, p90, and the share
within 100 px. Recordings made with ``benchmark_gaze.py record --all-engines``
also score the pupil-fit and MGazeNet sources. Nothing here is fitted on the
target it is scored on.
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_gaze import load_session  # noqa: E402
from app.core.calibration.processor import new_model  # noqa: E402
from app.core.calibration.recenter import RECENTER_POINTS, fit_correction  # noqa: E402
from app.core.detection.blink_detector import BlinkDetector  # noqa: E402
from app.core.detection.iris_detector import eye_geometry_features, eyeball_features  # noqa: E402
from app.core.gaze.eyeball_mapper import DEFAULT_PITCH_GAIN, DEFAULT_YAW_GAIN, EyeballModel  # noqa: E402
from app.core.gaze.evaluation import SETTLE_S  # noqa: E402
from app.core.gaze.feature_sources import (  # noqa: E402
    EYE_MIDPOINT_FEATURE_SOURCE,
    GAZEFOLLOWER_FEATURE_SOURCE,
    features_for_source,
)

GEOMETRY_SOURCE = "eye_geometry_v1"
PUPIL_SOURCE = "eye_midpoint_pupil_v1"
SCREEN_CM = (34.4, 19.4)
CAMERA_ABOVE_CM = 0.8
# Ridge penalty on standardised columns; results were flat across 0.1-10.
RIDGE = 1.0
# Cross-sitting pairs scored when both recordings are given.
PAIRS = (("s4", "s5"), ("s5", "s4"), ("s2", "s3"), ("s3", "s2"), ("s3", "s4"), ("s4", "s3"))


def load(path: Path) -> dict:
    meta, trials, readings, _ = load_session(path)
    fw, fh = meta["camera"]["width"], meta["camera"]["height"]
    closed = BlinkDetector()
    rows = []
    for trial in trials:
        for r in readings:
            if not (trial.onset + SETTLE_S <= r.captured_at < trial.end):
                continue
            if not r.face_found or r.midpoint_features is None or not r.eye_line:
                continue
            if closed.classify(r.left_ear, r.right_ear) is not None:
                continue
            geometry = r.geometry_features or eye_geometry_features(
                r.midpoint_features, r.eye_line, fw, fh)
            rows.append((trial.goal.center, {
                "reading": r, "geometry": geometry,
                "eyeball": r.eyeball_features or eyeball_features(
                    r.eye_line, fw, fh, *r.midpoint_features[4:6]),
                "mid": r.midpoint_features[:2], "ratio": r.features[:2],
                "ear": (r.left_ear, r.right_ear), "pose": r.midpoint_features[4:6],
                "position": geometry[2:5],
            }))
    distance = float(np.median([s["position"][2] for _, s in rows]))
    return {"name": path.stem, "rows": rows, "screen": tuple(meta["screen"]), "z_cm": distance}


def _matrix(rows, keys) -> np.ndarray:
    if not keys:
        return np.zeros((len(rows), 0))
    return np.array([[v for k in keys for v in s[k]] for _, s in rows], dtype=float)


def _goal_weights(rows) -> np.ndarray:
    goals = [tuple(g) for g, _ in rows]
    counts = {g: goals.count(g) for g in set(goals)}
    w = np.array([1.0 / counts[g] for g in goals])
    return w / w.sum() * len(rows)


class Ridge:
    """Ridge on standardised columns; eye columns also get quadratic terms."""

    def __init__(self, eye, head=(), degree=2):
        self.eye, self.head, self.degree = list(eye), list(head), degree

    def _design(self, rows):
        e = (_matrix(rows, self.eye) - self.me) / self.se
        h = (_matrix(rows, self.head) - self.mh) / self.sh
        cols = [np.ones((len(rows), 1)), e, h]
        if self.degree >= 2 and e.shape[1]:
            i, j = np.triu_indices(e.shape[1])
            cols.append(e[:, i] * e[:, j])
        return np.hstack(cols)

    def fit(self, rows):
        e, h = _matrix(rows, self.eye), _matrix(rows, self.head)
        self.me, self.se = e.mean(0), np.maximum(e.std(0), 1e-9)
        self.mh, self.sh = h.mean(0), np.maximum(h.std(0), 1e-9)
        a = self._design(rows) * np.sqrt(_goal_weights(rows))[:, None]
        y = np.array([g for g, _ in rows], dtype=float) * np.sqrt(_goal_weights(rows))[:, None]
        penalty = RIDGE * np.eye(a.shape[1])
        penalty[0, 0] = 0.0
        self.coef = np.linalg.solve(a.T @ a + penalty, a.T @ y)
        return self

    def predict(self, rows):
        return self._design(rows) @ self.coef


class Kernel:
    """RBF regression on per-target mean features over a linear mean (OpenGazer-style GP)."""

    def __init__(self, eye, head=(), length=1.0, noise=0.1):
        self.keys, self.length, self.noise = list(eye) + list(head), length, noise

    def _x(self, rows):
        return (_matrix(rows, self.keys) - self.m) / self.s

    def _k(self, p, q):
        return np.exp(-((p[:, None, :] - q[None, :, :]) ** 2).sum(-1) / (2 * self.length ** 2))

    def fit(self, rows):
        x = _matrix(rows, self.keys)
        self.m, self.s = x.mean(0), np.maximum(x.std(0), 1e-9)
        xs, goals = self._x(rows), [tuple(g) for g, _ in rows]
        keys = sorted(set(goals))
        self.centres = np.array([np.median(xs[[g == k for g in goals]], axis=0) for k in keys])
        y = np.array(keys, dtype=float)
        a = np.hstack([np.ones((len(keys), 1)), self.centres])
        self.linear = np.linalg.solve(a.T @ a + 0.1 * np.eye(a.shape[1]), a.T @ y)
        k = self._k(self.centres, self.centres) + self.noise * np.eye(len(keys))
        self.alpha = np.linalg.solve(k, y - a @ self.linear)
        return self

    def predict(self, rows):
        x = self._x(rows)
        return np.hstack([np.ones((len(x), 1)), x]) @ self.linear + self._k(x, self.centres) @ self.alpha


class Production:
    """A production calibration model for ``source``, refit on the same folds."""

    def __init__(self, source: str, screen):
        self.source, self.screen = source, screen

    def _features(self, sample):
        if self.source == GEOMETRY_SOURCE:
            return sample["geometry"]
        return features_for_source(sample["reading"], self.source)

    def usable(self, rows):
        return [r for r in rows if self._features(r[1]) is not None]

    def fit(self, rows):
        sw, sh = self.screen
        geometry = {"screen_cm": SCREEN_CM, "camera_above_cm": CAMERA_ABOVE_CM}
        self.model = new_model(self.source, geometry)
        self.model.fit([(self._features(s), (g[0] / sw, g[1] / sh)) for g, s in rows])
        return self

    def predict(self, rows):
        return np.array([self.model.predict(self._features(s)) for _, s in rows]) * self.screen


class Eyeball(Production):
    """Per-eye eyeball rays (eyeball_mapper) at the given head-angle gains."""

    def __init__(self, screen, yaw_gain=DEFAULT_YAW_GAIN, pitch_gain=DEFAULT_PITCH_GAIN):
        super().__init__("eyeball", screen)
        self.gains = (yaw_gain, pitch_gain)

    def _features(self, sample):
        return sample["eyeball"]

    def fit(self, rows):
        sw, sh = self.screen
        self.model = EyeballModel(self.source, SCREEN_CM, CAMERA_ABOVE_CM, None, *self.gains)
        self.model.fit([(self._features(s), (g[0] / sw, g[1] / sh)) for g, s in rows])
        return self


# Head-angle gains tried by --eyeball-sweep: (yaw, pitch).
EYEBALL_SWEEP = tuple((yaw, pitch) for yaw in (-0.5, 0.0, 0.25, 0.5, 0.75, 1.0)
                      for pitch in (0.25, 0.5, 0.75, 1.0))


def estimators(eyeball_sweep: bool = False) -> dict:
    eyeball = {
        f"eyeball per-eye rays (yaw {yaw:+.2f}, pitch {pitch:.2f})":
            (lambda y, p: lambda s: Eyeball(s["screen"], y, p))(yaw, pitch)
        for yaw, pitch in (EYEBALL_SWEEP if eyeball_sweep
                           else ((DEFAULT_YAW_GAIN, DEFAULT_PITCH_GAIN),))
    }
    return {
        **eyeball,
        "production geometric (eye_geometry_v1)": lambda s: Production(GEOMETRY_SOURCE, s["screen"]),
        "production eye-midpoint regression": lambda s: Production(EYE_MIDPOINT_FEATURE_SOURCE, s["screen"]),
        "production pupil-fit midpoint": lambda s: Production(PUPIL_SOURCE, s["screen"]),
        "production MGazeNet (appearance)": lambda s: Production(GAZEFOLLOWER_FEATURE_SOURCE, s["screen"]),
        "A: corner/lid ratios": lambda s: Ridge(["ratio"]),
        "A: midpoint + eyelid aperture": lambda s: Ridge(["mid", "ear"]),
        "B: midpoint + head pose/position": lambda s: Ridge(["mid"], ["pose", "position"]),
        "A+B: midpoint + lids + head": lambda s: Ridge(["mid", "ear"], ["pose", "position"]),
        "D: midpoint linear": lambda s: Ridge(["mid"], degree=1),
        "D: midpoint RBF kernel": lambda s: Kernel(["mid"]),
        "control: head only": lambda s: Ridge([], ["pose", "position"]),
    }


def _rows_for(estimator, rows):
    return estimator.usable(rows) if hasattr(estimator, "usable") else rows


def first_frames(rows, limit: int | None):
    """Keep the first ``limit`` settled frames of each target: a calibration dot of that length."""
    if limit is None:
        return rows
    seen: dict = {}
    kept = []
    for row in rows:
        key = tuple(row[0])
        seen[key] = seen.get(key, 0) + 1
        if seen[key] <= limit:
            kept.append(row)
    return kept


def _offsets(prediction, rows, exclude=()):
    goals = [tuple(g) for g, _ in rows]
    out = []
    for key in sorted(set(goals) - set(exclude)):
        idx = [i for i, g in enumerate(goals) if g == key]
        out.append(np.median(prediction[idx], axis=0) - np.array(key))
    return out


def within(session, make, train_frames=None):
    rows = _rows_for(make(session), session["rows"])
    offsets = []
    for key in sorted({tuple(g) for g, _ in rows}):
        train = first_frames([r for r in rows if tuple(r[0]) != key], train_frames)
        test = [r for r in rows if tuple(r[0]) == key]
        offsets += _offsets(make(session).fit(train).predict(test), test)
    return np.array(offsets)


def _recentre_goals(goals, screen):
    sw, sh = screen
    picked = []
    for dx, dy in RECENTER_POINTS:
        goal = min(goals, key=lambda g: (g[0] / sw - dx) ** 2 + (g[1] / sh - dy) ** 2)
        if goal not in picked:
            picked.append(goal)
    return picked


def cross(train, test, make, recentre=False, train_frames=None):
    estimator = make(train)
    estimator.fit(first_frames(_rows_for(estimator, train["rows"]), train_frames))
    rows = _rows_for(estimator, test["rows"])
    if not rows:
        raise ValueError(f"{test['name']} has no frames with this source")
    prediction = estimator.predict(rows)
    if not recentre:
        return np.array(_offsets(prediction, rows))
    sw, sh = test["screen"]
    goals = [tuple(g) for g, _ in rows]
    dots = _recentre_goals(sorted(set(goals)), test["screen"])
    pairs = [(tuple(np.median(prediction[[g == d for g in goals]], axis=0) / (sw, sh)),
              (d[0] / sw, d[1] / sh)) for d in dots]
    try:
        correction, _ = fit_correction(pairs)
    except ValueError:
        # The production re-centre would refuse this fit and keep the old mapping.
        return np.array(_offsets(prediction, rows, exclude=dots))
    corrected = np.array([correction.apply(x / sw, y / sh) for x, y in prediction]) * (sw, sh)
    return np.array(_offsets(corrected, rows, exclude=dots))


def summary(offsets, z_cm: float) -> str:
    if len(offsets) == 0:
        return "no data"
    err = np.hypot(offsets[:, 0], offsets[:, 1])
    deg = math.degrees(math.atan2(np.median(err) * SCREEN_CM[0] / 1920, z_cm))
    return (f"{np.median(err):5.0f} px {deg:4.1f} deg | |x| {np.median(np.abs(offsets[:, 0])):4.0f}"
            f" |y| {np.median(np.abs(offsets[:, 1])):4.0f} | p90 {np.percentile(err, 90):5.0f}"
            f" | <=100px {np.mean(err <= 100):4.0%}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("sessions", type=Path, nargs="+")
    parser.add_argument("--train-frames", type=int,
                        help="fit on only the first N settled frames per target (calibration dot length)")
    parser.add_argument("--only", help="run only estimators whose label contains this text")
    parser.add_argument("--eyeball-sweep", action="store_true",
                        help="score the eyeball model over a grid of head-angle gains")
    args = parser.parse_args()
    sessions = {p.stem: load(p) for p in args.sessions}
    for s in sessions.values():
        print(f"{s['name']}: {len(s['rows'])} frames, {len({tuple(g) for g, _ in s['rows']})} "
              f"targets, eye distance {s['z_cm']:.0f} cm")
    pairs = [(a, b) for a, b in PAIRS if a in sessions and b in sessions]
    for label, make in estimators(args.eyeball_sweep).items():
        if args.only and args.only not in label:
            continue
        print(f"\n## {label}")
        for s in sessions.values():
            try:
                print(f"  within {s['name']:<14} {summary(within(s, make, args.train_frames), s['z_cm'])}")
            except (ValueError, np.linalg.LinAlgError) as exc:
                print(f"  within {s['name']:<14} not available ({exc})")
        for a, b in pairs:
            for recentre in (False, True):
                name = f"{a}->{b}" + (" +recentre" if recentre else "")
                try:
                    offsets = cross(sessions[a], sessions[b], make, recentre, args.train_frames)
                    print(f"  {name:<21} {summary(offsets, sessions[b]['z_cm'])}")
                except (ValueError, np.linalg.LinAlgError) as exc:
                    print(f"  {name:<21} not available ({exc})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
