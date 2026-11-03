import pytest

from app.core.gaze.estimator import GazeReading
from app.core.gaze.evaluation import (
    HOLD_S,
    SETTLE_S,
    CursorSample,
    Trial,
    accuracy_summary,
    button_layout,
    held_out_signal_models,
    per_target,
    pixels_to_degrees,
    pose_correlations,
    score_session,
)
from app.core.gaze.feature_sources import NOSE_EYE_FEATURE_SOURCE

FRAME_S = 0.05


def _trial(cx=960, cy=540, onset=0.0, end=2.5):
    goal, targets = button_layout(cx, cy, 1920, 1080)
    return Trial(goal, onset, end, targets)


def _samples(points, onset=0.0):
    return [CursorSample(onset + i * FRAME_S, x, y) for i, (x, y) in enumerate(points)]


def test_button_layout_puts_the_goal_in_a_3x3_grid_and_clips_at_the_edge():
    goal, targets = button_layout(960, 540, 1920, 1080)
    assert goal.center == pytest.approx((960, 540), abs=1)
    assert len(targets) == 9
    _, corner = button_layout(30, 20, 1920, 1080)
    assert len(corner) == 4


def test_cursor_on_the_goal_scores_perfectly():
    trial = _trial()
    samples = _samples([trial.goal.center] * 50)
    score = score_session(samples, [trial])
    assert score["error_px_p50"] == 0.0
    assert score["jitter_px_rms"] == 0.0
    assert score["acquired_rate"] == 1.0
    assert score["acquire_ms_p50"] == pytest.approx(0.0)
    assert score["wrong_target_rate"] == 0.0


def test_late_arrival_counts_acquisition_time_and_hold():
    trial = _trial()
    arrive = 20  # frames
    points = [(200.0, 200.0)] * arrive + [trial.goal.center] * 30
    score = score_session(_samples(points), [trial])
    assert score["acquire_ms_p50"] == pytest.approx(arrive * FRAME_S * 1000)
    assert HOLD_S < 30 * FRAME_S


def test_resting_on_a_neighbour_is_a_wrong_target():
    trial = _trial()
    neighbour = next(t for t in trial.targets if t != trial.goal)
    score = score_session(_samples([neighbour.center] * 50), [trial])
    assert score["acquired_rate"] == 0.0
    assert score["wrong_target_rate"] == 1.0
    assert score["error_px_p50"] > 0


def test_only_settled_frames_count_toward_error():
    trial = _trial()
    settle_frames = int(SETTLE_S / FRAME_S)
    points = [(0.0, 0.0)] * settle_frames + [trial.goal.center] * 20
    assert score_session(_samples(points), [trial])["error_px_p95"] == 0.0


def test_degrees_from_pixels():
    # 96 px at 0.018 cm/px is 1.73 cm; at 55 cm that is ~1.8 degrees.
    assert pixels_to_degrees(96, 0.018, 55) == pytest.approx(1.80, abs=0.01)
    score = score_session(_samples([(1060.0, 540.0)] * 50), [_trial()], 0.018, 55)
    assert score["error_deg_p50"] == pytest.approx(pixels_to_degrees(100, 0.018, 55), abs=0.05)


def _feature_reading(t, features):
    return GazeReading(face_found=True, captured_at=t, nose_features=tuple(features))


def _grid_session(eye_gain, head_gain, rng):
    """Targets on a 6x4 grid; features carry the goal through the eyes and/or head."""
    trials, readings, t = [], [], 0.0
    for gx in (0.08, 0.25, 0.42, 0.58, 0.75, 0.92):
        for gy in (0.08, 0.36, 0.64, 0.92):
            trial = _trial(gx * 1920, gy * 1080, onset=t, end=t + 2.5)
            trials.append(trial)
            for i in range(50):
                ft = t + i * FRAME_S
                noise = rng.normal(0, 0.01, 6)
                readings.append(_feature_reading(ft, (
                    eye_gain * gx + noise[0], eye_gain * gy + noise[1],
                    head_gain * gx + noise[2], head_gain * gy + noise[3],
                    noise[4], head_gain * gy + noise[5])))
            t += 2.5
    return trials, readings, NOSE_EYE_FEATURE_SOURCE


def test_per_target_reports_bias_and_top_row_reach():
    top, low = _trial(480, 86, 0.0, 2.5), _trial(480, 900, 2.5, 5.0)
    samples = (_samples([(480.0, 386.0)] * 50, onset=0.0)
               + _samples([(480.0, 1000.0)] * 50, onset=2.5))
    summary = accuracy_summary(per_target(samples, [top, low]), 1080)
    assert summary["bias_y_px"] == pytest.approx(200.0)
    assert summary["top_row_targets"] == 1
    assert summary["top_row_reach_rate"] == 0.0
    assert summary["reach_rate"] == 0.5


def test_head_driven_session_is_explained_by_the_head_not_the_eyes(rng):
    trials, readings, source = _grid_session(eye_gain=0.0, head_gain=1.0, rng=rng)
    models = held_out_signal_models(readings, trials, source)
    assert models["head_only"]["error_px_p50"] < 60
    assert models["eye_only"]["error_px_p50"] > 3 * models["head_only"]["error_px_p50"]

    samples = [CursorSample(r.captured_at, 960.0, 540.0) for r in readings]
    pose = pose_correlations(readings, per_target(samples, trials), source)
    assert pose["goal_y_vs"]["pitch"] > 0.95
    assert abs(pose["goal_y_vs"]["eye_y"]) < 0.5
