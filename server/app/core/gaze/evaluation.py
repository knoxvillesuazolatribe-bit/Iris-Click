"""Objective scores for a recorded target-following session.

A session is a list of trials (one goal button shown from ``onset`` to
``end``, surrounded by distractor buttons) and the cursor samples a navigation
mode produced from the same recorded camera frames. Every mode is replayed on
identical input, so differences come from the pipeline alone; the user's own
reaction time (~200 ms) is common to all modes.
"""

import math
from dataclasses import dataclass

import numpy as np

from app.core.actions.target_snap import TargetRect
from app.core.detection.iris_detector import eye_geometry_features
from app.core.gaze.diagnostics import percentile
from app.core.gaze.feature_sources import (
    NOSE_EYE_FEATURE_SOURCE,
    NOSE_EYE_PUPIL_FEATURE_SOURCE,
    features_for_source,
)

# Eyes need ~0.5-0.8 s after onset to land and settle; accuracy and jitter
# are scored only after this.
SETTLE_S = 0.8
# A target counts as acquired once the cursor stays on it this long, about
# the time a deliberate wink needs.
HOLD_S = 0.25
# 64x40 px is a typical toolbar/tab button at 100% scaling; 16 px gaps
# match dense browser chrome.
BUTTON_W, BUTTON_H, BUTTON_GAP = 64, 40, 16


@dataclass(frozen=True)
class Trial:
    goal: TargetRect
    onset: float
    end: float
    targets: tuple[TargetRect, ...] = ()


@dataclass(frozen=True)
class CursorSample:
    t: float
    x: float
    y: float


def button_layout(cx: float, cy: float, screen_w: int, screen_h: int) -> tuple[TargetRect, tuple]:
    """A goal button near (cx, cy), kept on screen, in a 3x3 grid of look-alikes."""
    cx = min(max(cx, BUTTON_W / 2), screen_w - BUTTON_W / 2)
    cy = min(max(cy, BUTTON_H / 2), screen_h - BUTTON_H / 2)
    targets = []
    goal = None
    for row in (-1, 0, 1):
        for col in (-1, 0, 1):
            left = int(cx - BUTTON_W / 2 + col * (BUTTON_W + BUTTON_GAP))
            top = int(cy - BUTTON_H / 2 + row * (BUTTON_H + BUTTON_GAP))
            rect = TargetRect(left, top, left + BUTTON_W, top + BUTTON_H,
                              "goal" if row == col == 0 else "")
            if rect.left < 0 or rect.top < 0 or rect.right > screen_w or rect.bottom > screen_h:
                continue
            targets.append(rect)
            if row == col == 0:
                goal = rect
    return goal, tuple(targets)


def pixels_to_degrees(pixels: float, cm_per_px: float, distance_cm: float) -> float:
    return math.degrees(math.atan2(pixels * cm_per_px, distance_cm))


def eye_distance_cm(readings, frame_w: int, frame_h: int) -> float | None:
    """Median eye-to-camera distance of a recording, from the apparent eye spacing.

    Degrees depend on it: 182 px is 3.4 deg at an assumed 55 cm but 4.7 deg
    at the 40 cm s4 was recorded from.
    """
    distances = [g[4] for r in readings
                 if r.face_found and (g := eye_geometry_features(
                     r.midpoint_features, r.eye_line, frame_w, frame_h)) is not None]
    return float(np.median(distances)) if distances else None


def _acquisition_time(samples, trial: Trial):
    """Seconds from onset until the cursor first holds on the goal, or None."""
    on_since = None
    for sample in samples:
        if trial.goal.distance_to(sample.x, sample.y) == 0.0:
            if on_since is None:
                on_since = sample.t
            if sample.t - on_since >= HOLD_S:
                return on_since - trial.onset
        else:
            on_since = None
    return None


def score_session(samples: list[CursorSample], trials: list[Trial],
                  cm_per_px: float | None = None, distance_cm: float | None = None) -> dict:
    errors, steps, acquire_times = [], [], []
    acquired = wrong_frames = settled_frames = 0
    for trial in trials:
        in_trial = [s for s in samples if trial.onset <= s.t < trial.end]
        settled = [s for s in in_trial if s.t >= trial.onset + SETTLE_S]
        gx, gy = trial.goal.center
        errors += [math.hypot(s.x - gx, s.y - gy) for s in settled]
        steps += [math.hypot(b.x - a.x, b.y - a.y) for a, b in zip(settled, settled[1:])]
        settled_frames += len(settled)
        others = [t for t in trial.targets if t != trial.goal]
        # Where a wink would click a neighbouring button instead of the goal.
        wrong_frames += sum(1 for s in settled
                            if any(t.distance_to(s.x, s.y) == 0.0 for t in others))
        elapsed = _acquisition_time(in_trial, trial)
        if elapsed is not None:
            acquired += 1
            acquire_times.append(elapsed * 1000.0)

    ordered = sorted(errors)
    result = {
        "trials": len(trials),
        "error_px_p50": percentile(ordered, 0.50),
        "error_px_p95": percentile(ordered, 0.95),
        # RMS frame-to-frame motion while the user holds still on a target.
        "jitter_px_rms": math.sqrt(sum(d * d for d in steps) / len(steps)) if steps else math.nan,
        "acquired_rate": acquired / len(trials) if trials else math.nan,
        "acquire_ms_p50": percentile(sorted(acquire_times), 0.50),
        "wrong_target_rate": wrong_frames / settled_frames if settled_frames else math.nan,
    }
    if cm_per_px and distance_cm:
        for key in ("error_px_p50", "error_px_p95"):
            result[key.replace("px", "deg")] = pixels_to_degrees(result[key], cm_per_px,
                                                                 distance_cm)
    return result


# "Reached" means the cursor came this close to the goal centre at least once
# during the trial: about the calibrated webcam error (~100 px at 1080p).
REACH_PX = 100.0
# Goals in the top fifth of the screen: tabs, address bar, window buttons.
TOP_ROW_FRACTION = 0.2
# Ridge penalty for the held-out signal models, on standardised columns with
# every target weighted 1 in total.
SIGNAL_RIDGE = 0.5

_NOSE_SOURCES = (NOSE_EYE_FEATURE_SOURCE, NOSE_EYE_PUPIL_FEATURE_SOURCE)


@dataclass(frozen=True)
class TargetResult:
    trial: Trial
    goal: tuple[float, float]
    median: tuple[float, float]
    spread: tuple[float, float]
    reached: bool

    @property
    def offset(self) -> tuple[float, float]:
        return self.median[0] - self.goal[0], self.median[1] - self.goal[1]

    @property
    def error(self) -> float:
        return math.hypot(*self.offset)


def per_target(samples: list[CursorSample], trials: list[Trial]) -> list[TargetResult]:
    """Median settled cursor, its spread (std px) and reach, for each trial."""
    results = []
    for trial in trials:
        in_trial = [s for s in samples if trial.onset <= s.t < trial.end]
        settled = np.array([(s.x, s.y) for s in in_trial if s.t >= trial.onset + SETTLE_S])
        if len(settled) < 3:
            continue
        gx, gy = trial.goal.center
        reached = any(math.hypot(s.x - gx, s.y - gy) <= REACH_PX for s in in_trial)
        results.append(TargetResult(trial, (gx, gy), tuple(np.median(settled, axis=0)),
                                    tuple(np.std(settled, axis=0)), reached))
    return results


def accuracy_summary(results: list[TargetResult], screen_h: int,
                     cm_per_px: float | None = None, distance_cm: float | None = None) -> dict:
    """Per-target (not per-frame) accuracy: each target counts once."""
    if not results:
        return {}
    errors = sorted(r.error for r in results)
    offsets = np.array([r.offset for r in results])
    top = [r for r in results if r.goal[1] < TOP_ROW_FRACTION * screen_h]
    summary = {
        "targets": len(results),
        "error_px_p50": percentile(errors, 0.50),
        "error_px_p95": percentile(errors, 0.95),
        "bias_x_px": float(offsets[:, 0].mean()),
        "bias_y_px": float(offsets[:, 1].mean()),
        "spread_px": float(np.median([math.hypot(*r.spread) for r in results])),
        "reach_rate": sum(r.reached for r in results) / len(results),
        "top_row_targets": len(top),
        "top_row_reach_rate": sum(r.reached for r in top) / len(top) if top else math.nan,
        "top_row_bias_y_px": float(np.mean([r.offset[1] for r in top])) if top else math.nan,
    }
    if cm_per_px and distance_cm:
        summary["error_deg_p50"] = pixels_to_degrees(summary["error_px_p50"], cm_per_px,
                                                     distance_cm)
    return summary


def feature_names(source: str) -> tuple[str, ...]:
    if source in _NOSE_SOURCES:
        return "eye_x", "eye_y", "apex_x", "apex_y", "yaw", "pitch"
    return "gaze_x", "gaze_y", "eye_diff_x", "eye_diff_y", "yaw", "pitch"


def signal_columns(source: str) -> dict[str, tuple[int, ...]]:
    """Feature columns driven by the eyes, by the head, and both."""
    if source in _NOSE_SOURCES:
        eye, head = (0, 1), (2, 3, 4, 5)
    else:
        eye, head = (0, 1, 2, 3), (4, 5)
    return {"eye_only": eye, "head_only": head, "combined": eye + head}


def _settled_features(readings, trial: Trial, source: str):
    return [f for r in readings
            if trial.onset + SETTLE_S <= r.captured_at < trial.end
            and (f := features_for_source(r, source)) is not None]


def _pearson(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if len(a) < 3 or np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return math.nan
    return float(np.corrcoef(a, b)[0, 1])


def pose_correlations(readings, results: list[TargetResult], source: str) -> dict:
    """How each feature follows the goal's height, and the vertical error.

    A vertical target position explained by pitch/apex rather than eye_y
    means the user aims up/down with the head.
    """
    goal_y, error_y, medians = [], [], []
    for result in results:
        features = _settled_features(readings, result.trial, source)
        if len(features) < 3:
            continue
        goal_y.append(result.goal[1])
        error_y.append(result.offset[1])
        medians.append(np.median(np.array(features), axis=0))
    if len(medians) < 3:
        return {}
    medians = np.array(medians)
    names = feature_names(source)
    return {
        "goal_y_vs": {n: _pearson(goal_y, medians[:, i]) for i, n in enumerate(names)},
        "error_y_vs": {n: _pearson(error_y, medians[:, i]) for i, n in enumerate(names)},
    }


def _design(features: np.ndarray, mean: np.ndarray, scale: np.ndarray) -> np.ndarray:
    z = (features - mean) / scale
    return np.hstack([np.ones((len(z), 1)), z, z * z])


def held_out_signal_models(readings, trials: list[Trial], source: str) -> dict:
    """Leave-one-target-out error of eye-only, head-only and combined models.

    Each model is a ridge regression on linear + squared terms of its
    columns, fitted on the session's other targets and scored on the median
    prediction for the held-out one. It measures how much screen position the
    signals carry, independent of the saved calibration.
    """
    per_trial = [(np.array(f), np.array(t.goal.center)) for t in trials
                 if len(f := _settled_features(readings, t, source)) >= 3]
    if len(per_trial) < 6:
        return {}
    report = {}
    for name, columns in signal_columns(source).items():
        errors, errors_y = [], []
        for held in range(len(per_trial)):
            train = [p for i, p in enumerate(per_trial) if i != held]
            x = np.vstack([f[:, columns] for f, _ in train])
            y = np.vstack([np.repeat(g[None, :], len(f), axis=0) for f, g in train])
            weights = np.concatenate([np.full(len(f), 1.0 / len(f)) for f, _ in train])
            mean = np.average(x, axis=0, weights=weights)
            scale = np.maximum(np.sqrt(np.average((x - mean) ** 2, axis=0, weights=weights)),
                               1e-6)
            a = _design(x, mean, scale) * np.sqrt(weights)[:, None]
            penalty = SIGNAL_RIDGE * np.eye(a.shape[1])
            penalty[0, 0] = 0.0
            coef = np.linalg.solve(a.T @ a + penalty, a.T @ (y * np.sqrt(weights)[:, None]))
            features, goal = per_trial[held]
            predicted = np.median(_design(features[:, columns], mean, scale) @ coef, axis=0)
            errors.append(float(np.hypot(*(predicted - goal))))
            errors_y.append(float(abs(predicted[1] - goal[1])))
        report[name] = {"error_px_p50": float(np.median(errors)),
                        "error_px_mean": float(np.mean(errors)),
                        "abs_error_y_px_p50": float(np.median(errors_y))}
    return report
