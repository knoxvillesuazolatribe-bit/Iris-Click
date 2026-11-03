import pytest

from app.core.gaze.edge_reach import EDGE_LEVELS, apply_edge_reach, next_edge_level

MAX_X = 1919.0


def _at(fraction, level):
    return apply_edge_reach(fraction * MAX_X, MAX_X, level) / MAX_X


def test_off_changes_nothing():
    assert _at(0.02, "off") == pytest.approx(0.02)


@pytest.mark.parametrize("level, trigger, knee", [("low", 0.05, 0.25), ("medium", 0.10, 0.30),
                                                  ("high", 0.15, 0.35)])
def test_the_cursor_reaches_the_side_only_at_the_trigger(level, trigger, knee):
    assert _at(trigger, level) == pytest.approx(0.0)
    assert _at(trigger + 0.02, level) > 0.0
    assert _at(1.0 - trigger, level) == pytest.approx(1.0)
    assert _at(1.0 - trigger - 0.02, level) < 1.0
    # Continuous at the knee, so crossing it never jumps.
    assert _at(knee, level) == pytest.approx(knee)
    assert _at(knee - 1e-6, level) == pytest.approx(knee, abs=1e-4)
    assert _at(0.5, level) == pytest.approx(0.5)


def test_a_normal_side_glance_stops_short_of_the_edge():
    assert _at(0.20, "medium") == pytest.approx(0.15)


def test_a_position_past_the_side_stays_on_screen():
    assert _at(-0.2, "medium") == pytest.approx(0.0)
    assert _at(1.2, "medium") == pytest.approx(1.0)


def test_higher_levels_need_less_eye_travel():
    positions = [_at(0.20, level) for level in ("low", "medium", "high")]
    assert positions == sorted(positions, reverse=True)


def test_levels_cycle_through_all_and_wrap():
    level, seen = "off", []
    for _ in EDGE_LEVELS:
        level = next_edge_level(level)
        seen.append(level)
    assert seen == ["low", "medium", "high", "off"]
