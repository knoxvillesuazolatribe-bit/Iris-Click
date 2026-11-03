import math

import numpy as np
import pytest

from app.core.actions.target_snap import TargetRect
from app.core.gaze.estimator import GazeReading
from app.core.gaze.navigation import CursorNavigator, NavigationConfig
from app.core.gaze.pipeline import GazeEstimate

SCREEN = (1920, 1080)
FRAME_S = 1 / 22


def _reading(t, apex=(0.0, 1.0)):
    return GazeReading(face_found=True, features=(0.5, 0.5, 0.0, 0.0, 0.0, 0.0),
                       captured_at=t, eye_line={"nose_apex": apex})


def _run(navigator, points, start=1.0, apex=(0.0, 1.0), targets=()):
    """Feed raw (and identical pipeline) points one frame apart; return the steps."""
    steps = []
    for i, (x, y) in enumerate(points):
        t = start + i * FRAME_S
        steps.append(navigator.update(GazeEstimate(x, y, x, y), _reading(t, apex), targets, t))
    return steps


def _navigator(mode, **overrides):
    return CursorNavigator(NavigationConfig(mode=mode, **overrides), *SCREEN)


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        NavigationConfig(mode="fast")


def test_raw_mode_passes_the_prediction_through_clipped():
    steps = _run(_navigator("raw"), [(100.0, 200.0), (-50.0, 5000.0)])
    assert (steps[0].x, steps[0].y) == (100.0, 200.0)
    assert (steps[1].x, steps[1].y) == (0.0, 1079.0)


def test_legacy_mode_holds_small_corrections_inside_the_fixation_radius():
    navigator = _navigator("legacy", head_enabled=False, snap_enabled=False)
    steps = _run(navigator, [(800.0, 500.0)] * 5 + [(860.0, 500.0)] * 3)
    # A 60 px correction moves only the 12-sample running mean.
    assert steps[-1].x < 840.0


def test_filtered_mode_follows_a_small_correction_that_legacy_holds_back():
    points = [(800.0, 500.0)] * 10 + [(860.0, 500.0)] * 6
    legacy = _run(_navigator("legacy", head_enabled=False, snap_enabled=False), points)
    filtered = _run(_navigator("filtered"), points)
    assert abs(filtered[-1].x - 860.0) < abs(legacy[-1].x - 860.0)
    assert abs(filtered[-1].x - 860.0) < 10.0


def test_filtered_mode_reduces_fixation_jitter(rng):
    noise = rng.normal(0, 25, size=(60, 2))
    points = [(960.0 + dx, 540.0 + dy) for dx, dy in noise]
    steps = _run(_navigator("filtered"), points)[20:]
    raw_jitter = np.std(noise[20:, 0])
    # Default tuning passes ~half of 25 px white noise; tune with the replay sweep.
    assert np.std([s.x for s in steps]) < raw_jitter * 0.6


def test_filtered_mode_reaches_a_saccade_target_within_a_few_frames():
    steps = _run(_navigator("filtered"), [(400.0, 500.0)] * 10 + [(1400.0, 500.0)] * 4)
    assert steps[-1].x > 1400.0 - 20.0


def test_head_mode_offsets_with_the_head_and_resets_on_a_gaze_jump():
    navigator = _navigator("head")
    _run(navigator, [(960.0, 540.0)] * 10, start=1.0, apex=(0.0, 1.0))
    turned = _run(navigator, [(960.0, 540.0)] * 30, start=2.0, apex=(0.05, 1.0))
    assert turned[-1].x > 960.0 + 50.0
    assert turned[-1].head_offset_px > 50.0
    jumped = _run(navigator, [(300.0, 540.0)] * 10, start=4.0, apex=(0.05, 1.0))
    assert jumped[-1].head_offset_px == 0.0


def test_filtered_mode_ignores_the_head():
    steps = _run(_navigator("filtered"), [(960.0, 540.0)] * 20, apex=(0.2, 1.0))
    assert steps[-1].head_offset_px == 0.0


def test_assisted_mode_snaps_onto_a_nearby_button():
    button = TargetRect(1000, 500, 1064, 540, "OK")
    steps = _run(_navigator("assisted"), [(990.0, 560.0)] * 10, targets=(button,))
    assert steps[-1].target == button
    assert (steps[-1].x, steps[-1].y) == button.center


def test_only_assisted_and_legacy_use_targets_and_raw_skips_glide():
    assert NavigationConfig(mode="assisted").uses_targets
    assert NavigationConfig(mode="legacy", snap_enabled=True).uses_targets
    assert not NavigationConfig(mode="legacy", snap_enabled=False).uses_targets
    assert not NavigationConfig(mode="filtered").uses_targets
    assert not NavigationConfig(mode="raw").glides


def test_deadzone_keeps_the_cursor_still_for_tiny_changes():
    steps = _run(_navigator("filtered", filter_mincutoff=50.0), [(960.0, 540.0)] * 5
                 + [(962.0, 541.0)] * 5)
    assert math.dist((steps[-1].x, steps[-1].y), (steps[4].x, steps[4].y)) == 0.0


def _steer_frames(navigator, frames, start=1.0):
    """frames: (gaze x, gaze y, apex x, apex y) one per FRAME_S."""
    steps = []
    for i, (x, y, ax, ay) in enumerate(frames):
        t = start + i * FRAME_S
        steps.append(navigator.update(GazeEstimate(x, y, x, y), _reading(t, (ax, ay)), (), t))
    return steps


def _rest(x, y, n, rng=None, noise=0.0, apex=(0.0, 1.0)):
    jitter = rng.normal(0, noise, size=(n, 2)) if rng is not None else np.zeros((n, 2))
    return [(x + dx, y + dy, *apex) for dx, dy in jitter]


def test_steer_follows_the_eyes_until_the_gaze_rests():
    navigator = _navigator("steer")
    moving = [(400.0 + 60 * i, 500.0, 0.0, 1.0) for i in range(8)]
    assert not any(s.fine for s in _steer_frames(navigator, moving))


def test_steer_freezes_eye_jitter_once_the_gaze_rests(rng):
    navigator = _navigator("steer")
    steps = _steer_frames(navigator, _rest(900.0, 500.0, 40, rng, noise=25.0))
    fine = [s for s in steps if s.fine]
    assert len(fine) > 25
    assert np.std([s.x for s in fine]) < 1.0
    assert math.dist((fine[-1].x, fine[-1].y), (900.0, 500.0)) < 25.0


def test_head_turn_steers_the_frozen_cursor():
    navigator = _navigator("steer")
    _steer_frames(navigator, _rest(900.0, 500.0, 15))
    steps = _steer_frames(navigator, _rest(900.0, 500.0, 30, apex=(0.03, 0.98)), start=2.0)
    last = steps[-1]
    assert last.fine
    # 3000 px per apex unit beyond the 0.006 deadband: right and up.
    assert last.x == pytest.approx(900.0 + 3000 * 0.024, abs=8)
    assert last.y == pytest.approx(500.0 - 3000 * 0.014, abs=8)


def test_slow_eye_drift_during_a_head_turn_stays_in_fine_aim():
    navigator = _navigator("steer")
    _steer_frames(navigator, _rest(900.0, 500.0, 15))
    # Turning the head drags the eye estimate ~10 px per frame.
    drift = [(900.0 - 10 * i, 500.0, 0.0, 1.0) for i in range(30)]
    assert all(s.fine for s in _steer_frames(navigator, drift, start=2.0))


def test_a_quick_eye_jump_leaves_fine_aim():
    navigator = _navigator("steer")
    _steer_frames(navigator, _rest(900.0, 500.0, 15))
    # Confirmed after steer_exit_hold_s (0.1 s): four frames at 22 fps.
    steps = _steer_frames(navigator, [(1500.0, 300.0, 0.0, 1.0)] * 4, start=2.0)
    assert not steps[-1].fine
    assert steps[-1].x > 1300


def test_a_wink_keeps_the_steered_point():
    navigator = _navigator("steer")
    _steer_frames(navigator, _rest(900.0, 500.0, 15))
    before = _steer_frames(navigator, _rest(900.0, 500.0, 30, apex=(0.03, 1.0)), start=2.0)[-1]
    navigator.reset_fixation()
    after = _steer_frames(navigator, _rest(900.0, 500.0, 5, apex=(0.03, 1.0)), start=4.0)[-1]
    assert after.fine
    assert after.x == pytest.approx(before.x, abs=5)


def test_steer_uses_the_head_and_snapping_can_be_turned_off():
    config = NavigationConfig(mode="steer")
    assert config.uses_head and config.uses_targets and config.glides
    assert not NavigationConfig(mode="steer", snap_enabled=False).uses_targets


def _steer_with_targets(navigator, frames, targets, start=1.0):
    steps = []
    for i, (x, y, ax, ay) in enumerate(frames):
        t = start + i * FRAME_S
        steps.append(navigator.update(GazeEstimate(x, y, x, y), _reading(t, (ax, ay)), targets, t))
    return steps


def test_steer_snaps_to_a_nearby_button_once_the_gaze_rests():
    button = TargetRect(1000, 500, 1064, 540, "OK")
    steps = _steer_with_targets(_navigator("steer"), _rest(950.0, 560.0, 20), (button,))
    assert steps[-1].fine and steps[-1].target == button
    assert (steps[-1].x, steps[-1].y) == button.center


def test_steer_does_not_snap_while_the_eyes_are_moving():
    button = TargetRect(1000, 500, 1064, 540, "OK")
    moving = [(700.0 + 60 * i, 520.0, 0.0, 1.0) for i in range(8)]
    steps = _steer_with_targets(_navigator("steer"), moving, (button,))
    assert all(s.target is None for s in steps)


def test_a_quick_eye_jump_releases_the_snapped_button():
    button = TargetRect(1000, 500, 1064, 540, "OK")
    navigator = _navigator("steer")
    _steer_with_targets(navigator, _rest(950.0, 560.0, 20), (button,))
    jumped = _steer_with_targets(navigator, [(300.0, 200.0, 0.0, 1.0)] * 5, (button,), start=3.0)
    assert not jumped[-1].fine and jumped[-1].target is None
    assert jumped[-1].x < 700.0


def test_steer_stays_free_with_snapping_off():
    button = TargetRect(1000, 500, 1064, 540, "OK")
    navigator = _navigator("steer", snap_enabled=False)
    steps = _steer_with_targets(navigator, _rest(950.0, 560.0, 20), (button,))
    assert steps[-1].fine and steps[-1].target is None


def test_edge_sensitivity_moves_only_the_horizontal_side_zones():
    def settled(level, x, y):
        navigator = _navigator("filtered", edge_sensitivity=level)
        return _run(navigator, [(x, y)] * 40)[-1]

    # 192 px is 10% from the side: medium's trigger.
    assert settled("off", 192.0, 540.0).x > 150.0
    assert settled("medium", 192.0, 540.0).x < 10.0
    assert settled("medium", 1727.0, 540.0).x > 1909.0
    assert settled("medium", 960.0, 540.0).x == pytest.approx(960.0, abs=5)
    assert settled("medium", 960.0, 20.0).y == pytest.approx(20.0, abs=5)


def test_raw_mode_ignores_edge_sensitivity():
    steps = _run(_navigator("raw", edge_sensitivity="high"), [(192.0, 540.0)])
    assert steps[0].x == 192.0


def test_edge_sensitivity_changes_while_running():
    navigator = _navigator("filtered")
    navigator.set_edge_sensitivity("high")
    assert navigator.config.edge_sensitivity == "high"


def test_unknown_edge_sensitivity_is_rejected():
    with pytest.raises(ValueError):
        NavigationConfig(edge_sensitivity="max")
