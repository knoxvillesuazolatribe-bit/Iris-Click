import pytest

from app.core.gaze.head_nudge import HeadNudge


def _settle(nudge, apex, anchor, start, frames=30, step=1 / 30):
    t = start
    offset = (0.0, 0.0)
    for _ in range(frames):
        offset = nudge.update(apex, anchor, t)
        t += step
    return offset, t


def test_new_fixation_starts_without_offset():
    nudge = HeadNudge()
    assert nudge.update((0.0, 1.0), anchor_id=1, timestamp=0.0) == (0.0, 0.0)


def test_head_turn_right_moves_cursor_right_and_lift_moves_up():
    nudge = HeadNudge(gain_px=3000)
    _, t = _settle(nudge, (0.0, 1.0), anchor=1, start=0.0)
    (dx, dy), t = _settle(nudge, (0.03, 1.0), anchor=1, start=t)
    assert dx == pytest.approx(3000 * (0.03 - 0.006), rel=0.05)
    assert dy == pytest.approx(0.0, abs=1.0)
    (dx, dy), _ = _settle(nudge, (0.03, 0.97), anchor=1, start=t)
    assert dy < -50


def test_jitter_inside_deadband_does_not_move_cursor():
    nudge = HeadNudge()
    _, t = _settle(nudge, (0.0, 1.0), anchor=1, start=0.0)
    (dx, dy), _ = _settle(nudge, (0.004, 1.003), anchor=1, start=t)
    assert (dx, dy) == (0.0, 0.0)


def test_offset_is_capped_and_resets_on_new_fixation():
    nudge = HeadNudge(gain_px=3000, max_offset_px=200)
    _, t = _settle(nudge, (0.0, 1.0), anchor=1, start=0.0)
    (dx, dy), t = _settle(nudge, (0.5, 1.0), anchor=1, start=t)
    assert dx == pytest.approx(200, abs=1e-6)
    assert nudge.update((0.5, 1.0), anchor_id=2, timestamp=t) == (0.0, 0.0)


def test_missing_face_gives_no_offset():
    assert HeadNudge().update(None, anchor_id=1, timestamp=0.0) == (0.0, 0.0)
