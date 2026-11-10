"""Learn from every click: the learner, and its offline proof on simulated drift."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

from app.core.actions.target_snap import TargetRect
from app.core.gaze.evaluation import CursorSample, Trial, button_layout
from app.core.gaze.screen_mapper import ScreenCorrection
from app.workers import click_learning
from app.workers.click_learning import ClickLearner, remove_correction

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import compare_filters  # noqa: E402
import evaluate_click_learning as ev  # noqa: E402

SCREEN = (1920, 1080)
DRIFT = ScreenCorrection([[1.0, 0.0, 0.05], [0.0, 1.0, -0.04]])  # mapping 96 px right, 43 px up


def button(cx, cy, w=64, h=40):
    return TargetRect(int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2))


def clicks_with_drift(learner, points, correction=None):
    """Simulated snapped clicks: the mapping is off by DRIFT; returns the last update."""
    current = correction
    for fx, fy in points:
        mapped = DRIFT.apply(fx, fy)  # where the uncorrected mapping puts the true gaze
        shown = current.apply(*mapped) if current is not None else mapped
        updated = learner.observe_click((shown[0] * SCREEN[0], shown[1] * SCREEN[1]),
                                        button(fx * SCREEN[0], fy * SCREEN[1]), SCREEN, current)
        if updated is not None:
            current = updated
    return current


POINTS = [(0.2, 0.2), (0.8, 0.2), (0.5, 0.5), (0.2, 0.8), (0.8, 0.8), (0.35, 0.65), (0.65, 0.35)]


def test_off_by_default_and_never_acts():
    learner = ClickLearner()
    assert learner.observe_click((100, 100), button(120, 110), SCREEN, None) is None
    assert len(learner.pairs) == 0


def test_env_switch(monkeypatch):
    monkeypatch.setenv(click_learning.ENV_NAME, "on")
    assert click_learning.enabled_from_env() is True
    monkeypatch.setenv(click_learning.ENV_NAME, "off")
    assert click_learning.enabled_from_env() is False


def test_needs_enough_clicks_then_moves_part_of_the_way():
    learner = ClickLearner(enabled=True)
    assert clicks_with_drift(learner, POINTS[:4]) is None  # 4 < MIN_PAIRS
    corrected = clicks_with_drift(ClickLearner(enabled=True), POINTS[:5])
    assert corrected is not None
    # One update moves 30% of the way: the x shift is about -0.3 * 0.05.
    assert corrected.matrix[0, 2] == pytest.approx(-0.3 * 0.05, abs=0.005)
    assert corrected.matrix[1, 2] == pytest.approx(0.3 * 0.04, abs=0.005)


def test_repeated_learning_removes_the_drift():
    learner = ClickLearner(enabled=True)
    current = None
    for _ in range(6):
        current = clicks_with_drift(learner, POINTS, current) or current
    fx, fy = 0.5, 0.5
    seen = current.apply(*DRIFT.apply(fx, fy))
    assert math.hypot((seen[0] - fx) * SCREEN[0], (seen[1] - fy) * SCREEN[1]) < 15


def test_big_or_far_targets_are_ignored():
    learner = ClickLearner(enabled=True)
    assert learner.observe_click((500, 500), button(510, 505, w=300, h=200), SCREEN, None) is None
    assert learner.observe_click((100, 100), button(900, 700), SCREEN, None) is None
    assert learner.observe_click((100, 100), None, SCREEN, None) is None
    assert learner.observe_click(None, button(100, 100), SCREEN, None) is None
    assert len(learner.pairs) == 0


def test_clicks_bunched_in_one_spot_are_not_enough():
    learner = ClickLearner(enabled=True, min_pairs=3)
    # All clicks at the same spot cannot measure scale: no correction yet.
    for _ in range(6):
        assert learner.observe_click((960, 540), button(970, 545), SCREEN, None) is None


def test_reset_forgets_pairs():
    learner = ClickLearner(enabled=True)
    learner.observe_click((960, 540), button(970, 545), SCREEN, None)
    learner.reset()
    assert len(learner.pairs) == 0


def test_remove_correction_inverts_the_affine():
    correction = ScreenCorrection([[1.1, 0.05, -0.02], [0.03, 0.9, 0.04]])
    x, y = correction.apply(0.3, 0.7)
    assert remove_correction(correction, x, y) == pytest.approx((0.3, 0.7))


# ---- offline evaluator on simulated recordings
def simulated_session(drift_after=0, seed=1):
    """Raw cursor samples that follow 24 goals with noise; drift appears after ``drift_after`` trials."""
    rng = np.random.default_rng(seed)
    trials, samples, t = [], [], 0.0
    grid = [(x, y) for y in (0.1, 0.36, 0.64, 0.9) for x in (0.1, 0.3, 0.5, 0.7, 0.9, 0.5)]
    for i, (fx, fy) in enumerate(grid):
        goal, targets = button_layout(fx * SCREEN[0], fy * SCREEN[1], *SCREEN)
        trials.append(Trial(goal, t, t + 2.5, targets))
        gx, gy = goal.center
        for k in range(75):
            st = t + k / 30
            px, py = gx / SCREEN[0], gy / SCREEN[1]
            if i >= drift_after:
                px, py = DRIFT.apply(px, py)
            samples.append(CursorSample(st, px * SCREEN[0] + rng.normal(0, 8), py * SCREEN[1] + rng.normal(0, 8)))
        t += 2.5
    return samples, trials


def test_evaluator_shows_learning_removes_drift():
    samples, trials = simulated_session(drift_after=0)
    rows = ev.compare(samples, trials, SCREEN)
    assert rows["learning"]["clicks_used"] >= 20
    assert rows["learning"]["updates"] > 0
    fixed_late = rows["fixed"]["error_px_p50_second_half"]
    learned_late = rows["learning"]["error_px_p50_second_half"]
    assert fixed_late > 90 and learned_late < fixed_late * 0.5


def test_evaluator_does_no_harm_without_drift():
    samples, trials = simulated_session(drift_after=10_000)
    rows = ev.compare(samples, trials, SCREEN)
    assert rows["learning"]["error_px_p50"] <= rows["fixed"]["error_px_p50"] + 5


def test_clicks_outside_the_snap_radius_are_not_used():
    samples, trials = simulated_session(drift_after=0)
    rows = ev.compare(samples, trials, SCREEN, snap_px=50)  # drift ~105 px > 50 px
    assert rows["learning"]["clicks_used"] == 0


# ---- offline filter comparison
def test_kalman_smooths_jitter_and_follows_a_jump():
    rng = np.random.default_rng(2)
    flt = compare_filters.KalmanFilter2D(200.0, 900.0)
    still = [flt(500 + rng.normal(0, 30), 500 + rng.normal(0, 30), i / 30) for i in range(60)]
    spread = np.std(np.array(still[20:]), axis=0)
    assert spread.max() < 20  # raw noise is 30 px
    for i in range(60, 150):  # it may overshoot a big jump, but must settle on it
        x, y = flt(1200.0, 500.0, i / 30)
    assert abs(x - 1200) < 25


def test_filter_comparison_scores_every_variant():
    samples, trials = simulated_session(drift_after=10_000)
    rows = compare_filters.compare(samples, trials, 0.8, 0.01)
    assert set(rows) >= {"none", "one-euro 0.8/0.01"} and any(k.startswith("kalman") for k in rows)
    assert rows["kalman q200 r900"]["jitter_px_rms"] < rows["none"]["jitter_px_rms"]
