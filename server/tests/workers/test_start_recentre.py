from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.workers import start_recentre
from app.workers.start_recentre import STEADY_S, StartRecentre, profile_age_s

FACE = SimpleNamespace(face_found=True, eye_line={"pointer": (0.5, 0.5)}, left_ear=0.3, right_ear=0.3)
NO_FACE = SimpleNamespace(face_found=False, eye_line=None, left_ear=1.0, right_ear=1.0)
CLOSED = SimpleNamespace(face_found=True, eye_line={"pointer": (0.5, 0.5)}, left_ear=0.05, right_ear=0.3)


def run(trigger, readings, start=0.0, step=0.1):
    """Feeds readings at 10 fps; returns the times it fired."""
    fired, t = [], start
    for reading in readings:
        if trigger.due(t, reading):
            fired.append(round(t, 2))
        t += step
    return fired


def test_fires_once_after_two_steady_seconds():
    trigger = StartRecentre(enabled=True, profile_age=3600)
    fired = run(trigger, [FACE] * 60)
    assert fired == [pytest.approx(STEADY_S, abs=0.11)]


def test_no_face_or_closed_eyes_restart_the_wait():
    trigger = StartRecentre(enabled=True, profile_age=3600)
    assert run(trigger, [FACE] * 15 + [NO_FACE] + [FACE] * 15 + [CLOSED] + [FACE] * 10) == []
    assert run(trigger, [FACE] * 25, start=10.0) != []


def test_nobody_in_front_never_fires():
    trigger = StartRecentre(enabled=True, profile_age=3600)
    assert run(trigger, [NO_FACE] * 200) == []
    assert trigger.pending


def test_skipped_for_a_fresh_calibration():
    assert not StartRecentre(enabled=True, profile_age=60).pending
    assert StartRecentre(enabled=True, profile_age=600).pending
    assert StartRecentre(enabled=True, profile_age=None).pending  # unknown age: re-centre


def test_switched_off():
    trigger = StartRecentre(enabled=False, profile_age=3600)
    assert run(trigger, [FACE] * 60) == []


@pytest.mark.parametrize("value, expected", [("off", False), ("OFF", False), ("0", False),
                                             ("on", True), ("1", True)])
def test_env_switch(monkeypatch, value, expected):
    monkeypatch.setenv(start_recentre.ENV_NAME, value)
    assert start_recentre.enabled_from_env() is expected


def test_default_is_on(monkeypatch, tmp_path):
    monkeypatch.delenv(start_recentre.ENV_NAME, raising=False)
    monkeypatch.setattr("app.config.SERVER_DIR", tmp_path)  # no .env there
    assert start_recentre.enabled_from_env() is True


def test_profile_age_from_its_id():
    now = datetime(2026, 11, 11, 9, 0, 0)
    assert profile_age_s("20261111T081351-619f6165", now) == pytest.approx(
        (now - datetime(2026, 11, 11, 8, 13, 51)).total_seconds())
    assert profile_age_s("not-a-profile", now) is None
    assert profile_age_s(None, now) is None
    stamp = (now - timedelta(minutes=2)).strftime("%Y%m%dT%H%M%S")
    assert StartRecentre(True, profile_age_s(stamp + "-abcd1234", now)).pending is False
