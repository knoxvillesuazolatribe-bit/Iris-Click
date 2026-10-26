from app.core.detection.blink_detector import BOTH, LEFT, RIGHT, BlinkDetector
from app.core.gaze.feature_sources import EYE_MIDPOINT_FEATURE_SOURCE, GAZEFOLLOWER_FEATURE_SOURCE
from app.core.gaze.pipeline import GazePipeline
from app.core.gaze.screen_mapper import CalibrationModel

from tests.factories import synthetic_reading
from .test_screen_mapper import _samples

OPEN, CLOSED = 0.30, 0.05


def _hold(detector, left, right, start, seconds, step=0.03):
    t = start
    event = None
    while t < start + seconds:
        event = detector.update(left, right, now=t) or event
        t += step
    return event, t


def test_left_wink_reported_on_reopen():
    detector = BlinkDetector()
    _, t = _hold(detector, CLOSED, OPEN, 0.0, 0.5)
    assert detector.update(OPEN, OPEN, now=t) == LEFT


def test_right_wink_reported_on_reopen():
    detector = BlinkDetector()
    _, t = _hold(detector, OPEN, CLOSED, 0.0, 0.5)
    assert detector.update(OPEN, OPEN, now=t) == RIGHT


def test_natural_blink_is_ignored():
    detector = BlinkDetector()
    _, t = _hold(detector, CLOSED, CLOSED, 0.0, 0.12)
    assert detector.update(OPEN, OPEN, now=t) is None


def test_wink_turning_into_full_blink_is_both():
    detector = BlinkDetector()
    _, t = _hold(detector, CLOSED, OPEN, 0.0, 0.1)
    _, t = _hold(detector, CLOSED, CLOSED, t, 0.4)
    assert detector.update(OPEN, OPEN, now=t) == BOTH


def test_cooldown_blocks_immediate_repeat():
    detector = BlinkDetector(cooldown_ms=700)
    _, t = _hold(detector, CLOSED, OPEN, 0.0, 0.4)
    assert detector.update(OPEN, OPEN, now=t) == LEFT
    _, t = _hold(detector, CLOSED, OPEN, t + 0.01, 0.4)
    assert detector.update(OPEN, OPEN, now=t) is None


def test_pipeline_falls_back_to_reference_when_deep_source_missing(rng):
    reference = CalibrationModel(feature_source=EYE_MIDPOINT_FEATURE_SOURCE)
    reference.fit(_samples(rng))
    deep = CalibrationModel(feature_source=GAZEFOLLOWER_FEATURE_SOURCE, reference_model=reference)
    deep.fit([((tx, ty, 0, 0, 0.02, -0.01), (tx, ty)) for (_, (tx, ty)) in _samples(rng)])
    pipeline = GazePipeline()

    estimate = pipeline.process(synthetic_reading((0.5, 0.5), rng, deep=False), deep,
                                output_size=(1000, 1000))

    assert estimate is not None
    assert pipeline.using_reference_model
    assert abs(estimate.raw_x - 500) < 40


def test_pipeline_rejects_closed_eyes(rng):
    model = CalibrationModel(feature_source=EYE_MIDPOINT_FEATURE_SOURCE)
    model.fit(_samples(rng))
    pipeline = GazePipeline()

    assert pipeline.process(synthetic_reading((0.5, 0.5), rng, left_ear=0.02), model) is None
    assert pipeline.reason == "eyes_closed"
