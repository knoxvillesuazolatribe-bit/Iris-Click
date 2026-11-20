"""Smoother gaze controls (Nov 2026): per-person winks, snap reach and escape,
click learning on by default, faster edge scroll. Both-eye blinks are unchanged."""

from collections import deque
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.core.actions.target_snap import (
    ESCAPE_PX,
    MAX_RADIUS_PX,
    MIN_RADIUS_PX,
    RELEASE_SECONDS,
    TargetLock,
    TargetRect,
    snap_radius_for,
)
from app.core.detection.blink_detector import (
    BALANCE_LIMITS,
    BOTH,
    LEFT,
    MAX_WINK_MS,
    RIGHT,
    WINK_GAP_S,
    BlinkDetector,
)
from app.workers import click_learning
from app.workers.edge_scroll import SCROLL_EVERY_S, EdgeScroller
from app.workers.tracking_worker import CLICK_GAZE_SKIP_S, TrackingWorker

OPEN, CLOSED = 0.30, 0.05
STEP = 0.03  # ~33 fps


def feed(detector, left, right, start, seconds):
    """Steady eyes for ``seconds``; returns (events, next time)."""
    events, t = [], start
    while t < start + seconds - 1e-9:
        event = detector.update(left, right, now=t)
        if event:
            events.append(event)
        t += STEP
    return events, t


# --- Winks: eye balance --------------------------------------------------------------------

def test_a_naturally_narrower_eye_is_learned_and_never_clicks():
    detector = BlinkDetector()
    # Left eye always looks narrower (0.17 vs 0.30): without balancing it reads as a wink.
    events, t = feed(detector, 0.17, 0.30, 0.0, 6.0)
    assert events == []
    assert detector.balance == pytest.approx(BALANCE_LIMITS[0])
    assert detector.classify(0.17, 0.30) is None


def test_after_learning_both_winks_still_work_for_uneven_eyes():
    detector = BlinkDetector()
    _, t = feed(detector, 0.17, 0.30, 0.0, 4.0)
    events, t = feed(detector, CLOSED, 0.30, t, 0.5)
    events += feed(detector, 0.17, 0.30, t, 0.9)[0]
    assert events == [LEFT]
    _, t = feed(detector, 0.17, 0.30, t + 0.9, 0.1)
    events, t = feed(detector, 0.17, CLOSED, t, 0.5)
    events += feed(detector, 0.17, 0.30, t, 0.3)[0]
    assert events == [RIGHT]


def test_even_eyes_keep_a_neutral_balance():
    detector = BlinkDetector()
    feed(detector, OPEN, OPEN, 0.0, 4.0)
    assert detector.balance == pytest.approx(1.0)


def test_the_balance_survives_a_reset():
    detector = BlinkDetector()
    feed(detector, 0.17, 0.30, 0.0, 4.0)
    detector.reset()
    assert detector.balance == pytest.approx(BALANCE_LIMITS[0])


# --- Winks: flicker and length -------------------------------------------------------------

def test_one_noisy_open_frame_does_not_cancel_a_wink():
    detector = BlinkDetector()
    _, t = feed(detector, CLOSED, OPEN, 0.0, 0.21)
    assert detector.update(OPEN, OPEN, now=t) is None  # a single flicker frame
    _, t = feed(detector, CLOSED, OPEN, t + WINK_GAP_S / 2, 0.21)
    assert detector.update(OPEN, OPEN, now=t) == LEFT


def test_two_separate_short_closures_are_not_a_wink():
    detector = BlinkDetector()
    _, t = feed(detector, CLOSED, OPEN, 0.0, 0.21)
    _, t = feed(detector, OPEN, OPEN, t, 0.2)
    _, t = feed(detector, CLOSED, OPEN, t, 0.21)
    assert detector.update(OPEN, OPEN, now=t) is None


def test_resting_one_eye_does_not_click():
    detector = BlinkDetector()
    _, t = feed(detector, CLOSED, OPEN, 0.0, MAX_WINK_MS / 1000 + 0.5)
    assert detector.update(OPEN, OPEN, now=t) is None


def test_an_ordinary_wink_still_clicks_once():
    detector = BlinkDetector()
    events, t = feed(detector, CLOSED, OPEN, 0.0, 0.5)
    events += feed(detector, OPEN, OPEN, t, 1.0)[0]
    assert events == [LEFT]


# --- Both-eye blinks: unchanged ------------------------------------------------------------

def test_a_natural_blink_still_does_nothing():
    detector = BlinkDetector()
    events, t = feed(detector, CLOSED, CLOSED, 0.0, 0.12)
    events += feed(detector, OPEN, OPEN, t, 0.5)[0]
    assert events == []


def test_a_deliberate_both_eye_blink_still_counts():
    detector = BlinkDetector()
    _, t = feed(detector, CLOSED, CLOSED, 0.0, 0.5)
    assert detector.update(OPEN, OPEN, now=t) == BOTH


def test_a_long_both_eye_closure_is_still_a_blink():
    """The 2 s limit is for one-eye winks only."""
    detector = BlinkDetector()
    _, t = feed(detector, CLOSED, CLOSED, 0.0, 2.6)
    assert detector.update(OPEN, OPEN, now=t) == BOTH


def test_short_both_eye_blinks_are_not_joined():
    """Flicker joining is for winks only: two quick natural blinks stay ignored."""
    detector = BlinkDetector()
    _, t = feed(detector, CLOSED, CLOSED, 0.0, 0.21)
    assert detector.update(OPEN, OPEN, now=t) is None
    _, t = feed(detector, CLOSED, CLOSED, t + WINK_GAP_S / 2, 0.21)
    assert detector.update(OPEN, OPEN, now=t) is None


def test_double_both_eye_blink_still_gives_two_events():
    detector = BlinkDetector()
    events, t = feed(detector, CLOSED, CLOSED, 0.0, 0.45)
    events += feed(detector, OPEN, OPEN, t, 0.4)[0]
    _, t = feed(detector, OPEN, OPEN, t, 0.4)
    events += feed(detector, CLOSED, CLOSED, t, 0.45)[0]
    _, t = feed(detector, CLOSED, CLOSED, t, 0.45)
    events.append(detector.update(OPEN, OPEN, now=t))
    assert events == [BOTH, BOTH]


# --- Snap reach from the person's aim ------------------------------------------------------

def test_snap_radius_follows_the_calibration_error():
    assert snap_radius_for(None, 1920, 1080, 140) == 140
    assert snap_radius_for(0.144, 1920, 1080, 140) == pytest.approx(172.8)
    assert snap_radius_for(0.02, 1920, 1080, 140) == MIN_RADIUS_PX
    assert snap_radius_for(0.5, 1920, 1080, 140) == MAX_RADIUS_PX
    assert snap_radius_for(float("nan"), 1920, 1080, 140) == 140


BUTTON = TargetRect(900, 500, 940, 530, "Send")


def test_moving_clearly_away_from_a_snapped_button_breaks_free():
    lock = TargetLock(radius=170)
    # Locked from 60 px left of the button (the person's usual aim error).
    assert lock.snap(840, 515, [BUTTON], now=0.0)[2] == BUTTON
    away = 840 - ESCAPE_PX - 10
    lock.snap(away, 515, [BUTTON], now=0.1)
    # The old rule held this until 1.35 x 170 = 230 px from the edge.
    assert lock.snap(away, 515, [BUTTON], now=0.1 + RELEASE_SECONDS)[2] is None


def test_jitter_near_a_snapped_button_keeps_the_lock():
    lock = TargetLock(radius=170)
    lock.snap(840, 515, [BUTTON], now=0.0)
    for i in range(20):
        x = 840 - (ESCAPE_PX - 20) * (i % 2)  # wobbles up to 70 px farther out
        assert lock.snap(x, 515, [BUTTON], now=0.05 * (i + 1))[2] == BUTTON


def test_a_lock_from_inside_the_button_still_releases_when_looking_away():
    lock = TargetLock(radius=170)
    lock.snap(920, 515, [BUTTON], now=0.0)
    lock.snap(700, 515, [BUTTON], now=0.1)
    assert lock.snap(700, 515, [BUTTON], now=0.1 + RELEASE_SECONDS)[2] is None


# --- Click learning ------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["", "on", "yes"])
def test_click_learning_is_on_unless_turned_off(monkeypatch, value):
    monkeypatch.setenv(click_learning.ENV_NAME, value)
    assert click_learning.enabled_from_env() is True


@pytest.mark.parametrize("value", ["off", "0", "false", "No"])
def test_click_learning_can_be_turned_off(monkeypatch, value):
    monkeypatch.setenv(click_learning.ENV_NAME, value)
    assert click_learning.enabled_from_env() is False


def test_the_gaze_behind_a_click_skips_the_lid_drag():
    history = deque([(9.50, 100.0, 100.0), (9.70, 200.0, 300.0), (9.85, 220.0, 320.0),
                     (9.96, 900.0, 900.0)])  # the last one: the lid already dragging
    worker = SimpleNamespace(_raw_history=history)
    assert TrackingWorker._gaze_before(worker, 10.0) == pytest.approx((210.0, 310.0))
    assert 10.0 - 9.96 < CLICK_GAZE_SKIP_S
    assert TrackingWorker._gaze_before(SimpleNamespace(_raw_history=deque()), 10.0) is None


def test_a_snapped_click_feeds_the_learner_and_updates_the_correction():
    seen = []

    class Learner:
        def observe_click(self, gaze, target, screen, correction):
            seen.append((gaze, target, screen, correction))
            return "new correction"

    model = SimpleNamespace(correction="old", set_correction=lambda c: setattr(model, "correction", c))
    worker = SimpleNamespace(model=model, click_learner=Learner(), _wink_gaze=(10.0, 20.0),
                             _wink_target=BUTTON, screen_w=1920, screen_h=1080)
    TrackingWorker._learn_from_click(worker)
    assert seen == [((10.0, 20.0), BUTTON, (1920, 1080), "old")]
    assert model.correction == "new correction"


# --- Edge scroll speeds up -----------------------------------------------------------------

def test_edge_scroll_speeds_up_the_longer_you_look():
    calls = []
    settings = get_settings().model_copy(update={"edge_scroll_enabled": True,
                                                 "edge_scroll_band": 0.08, "dwell_ms": 700})
    scroller = EdgeScroller(settings, 1920, 1080, wheel=lambda x, y, n: calls.append(n) or True)
    t = 0.0
    while t <= 0.7 + 4.0:
        scroller.update(900, 1070, t)  # bottom band: scroll down
        t += 0.02
    assert calls[0] == -1
    assert set(calls) == {-1, -2, -3}
    assert calls == sorted(calls, reverse=True)  # never slows down while looking
    steps = len(calls)
    assert steps == pytest.approx(4.0 / SCROLL_EVERY_S, abs=2)


def test_a_new_look_at_the_edge_starts_slow_again():
    calls = []
    settings = get_settings().model_copy(update={"edge_scroll_enabled": True,
                                                 "edge_scroll_band": 0.08, "dwell_ms": 700})
    scroller = EdgeScroller(settings, 1920, 1080, wheel=lambda x, y, n: calls.append(n) or True)
    t = 0.0
    while t <= 4.0:
        scroller.update(900, 10, t)
        t += 0.02
    scroller.update(900, 540, t)  # looks away
    calls.clear()
    t += 0.02
    while t <= 4.0 + 0.75:
        scroller.update(900, 10, t)
        t += 0.02
    assert calls == [1]
