"""Cursor smoothing: One Euro filter, fixation lock (GazeStabilizer) and the inter-frame glide."""

import math
import random

import pytest

from app.core.gaze.smoothing import CursorGlide, GazeStabilizer, OneEuroFilter, OneEuroFilter2D

FPS = 30.0


def run(filter_, values, start=0.0):
    return [filter_(v, start + i / FPS) for i, v in enumerate(values)]


# --- One Euro --------------------------------------------------------------------------------

def test_one_euro_steadies_jitter_while_the_eye_rests():
    rng = random.Random(7)
    noisy = [500 + rng.gauss(0, 20) for _ in range(120)]
    smoothed = run(OneEuroFilter(freq=FPS, mincutoff=0.8, beta=0.01), noisy)
    raw_spread = max(noisy[60:]) - min(noisy[60:])
    smooth_spread = max(smoothed[60:]) - min(smoothed[60:])
    # Real settings (mincutoff 0.8, beta 0.01): the spread is about halved (40 vs 83 px here).
    assert smooth_spread < raw_spread / 1.8
    assert abs(sum(smoothed[60:]) / 60 - 500) < 10


def test_one_euro_follows_a_fast_jump_quickly():
    values = [200.0] * 30 + [1400.0] * 30
    slow = run(OneEuroFilter(freq=FPS, mincutoff=0.8, beta=0.0), values)
    adaptive = run(OneEuroFilter(freq=FPS, mincutoff=0.8, beta=0.01), values)
    # Five frames (~170 ms) after the jump the adaptive filter is far closer to the target.
    assert abs(adaptive[35] - 1400) < abs(slow[35] - 1400) / 2
    assert adaptive[-1] == pytest.approx(1400, abs=15)


def test_one_euro_is_deterministic_and_resettable():
    values = [100.0, 140.0, 90.0, 300.0, 310.0]
    f = OneEuroFilter(freq=FPS)
    first = run(f, values)
    f.reset()
    assert run(f, values) == first


def test_one_euro_ignores_out_of_order_frames():
    f = OneEuroFilter(freq=FPS)
    f(100.0, 1.0)
    held = f(500.0, 1.1)
    assert f(900.0, 1.05) == held  # an older timestamp changes nothing


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_one_euro_refuses_non_finite_input(bad):
    with pytest.raises(ValueError):
        OneEuroFilter()(bad, 0.0)


def test_one_euro_refuses_bad_settings():
    with pytest.raises(ValueError):
        OneEuroFilter(freq=0)
    with pytest.raises(ValueError):
        OneEuroFilter(beta=-1)


def test_one_euro_2d_filters_each_axis_and_can_change_cutoff():
    f = OneEuroFilter2D(freq=FPS)
    assert f(10.0, 20.0, 0.0) == (10.0, 20.0)
    f.set_mincutoff(2.0)
    with pytest.raises(ValueError):
        f.set_mincutoff(0)


# --- Fixation lock ---------------------------------------------------------------------------

def test_small_wobble_stays_locked_on_the_fixation():
    stab = GazeStabilizer(radius=80)
    rng = random.Random(3)
    points = [stab.update(600 + rng.uniform(-40, 40), 400 + rng.uniform(-40, 40), i / FPS)
              for i in range(60)]
    assert stab.anchor_id == 1
    assert all(math.dist(p, (600, 400)) < 40 for p in points[12:])


def test_a_deliberate_shift_moves_the_lock():
    stab = GazeStabilizer(radius=80, confirm_s=0.06, confirm_frames=2)
    for i in range(10):
        stab.update(300, 300, i / FPS)
    t = 10 / FPS
    x, y = stab.update(1200, 300, t)
    assert (x, y) != (1200, 300)  # one frame is not enough
    x, y = stab.update(1210, 300, t + 0.07)
    assert (x, y) == (1210, 300) and stab.anchor_id == 2


def test_a_single_spike_does_not_move_the_cursor():
    stab = GazeStabilizer(radius=80)
    for i in range(10):
        stab.update(500, 500, i / FPS)
    before = stab.update(500, 500, 10 / FPS)
    assert stab.update(1500, 900, 11 / FPS) == before
    assert stab.update(500, 500, 12 / FPS) == before


def test_eyes_falling_out_of_sync_are_ignored():
    stab = GazeStabilizer(radius=80, eye_jump_limit=0.12)
    stab.update(500, 500, 0.0, eye_difference=(0.0, 0.0))
    assert stab.update(1400, 900, 0.03, eye_difference=(0.5, 0.0)) == (500, 500)


# --- Glide -----------------------------------------------------------------------------------

def test_the_glide_reaches_each_new_point_within_its_duration():
    glide = CursorGlide(min_duration=0.02, max_duration=0.06)
    assert glide.position(0.0) is None
    glide.set_target(100, 100, 0.0)
    glide.set_target(200, 100, 0.04)
    mid = glide.position(0.05)
    assert 100 < mid[0] < 200
    assert glide.position(0.04 + 0.06) == (200, 100)
    glide.reset()
    assert glide.position(1.0) is None
