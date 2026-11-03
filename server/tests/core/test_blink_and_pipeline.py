import pytest

from app.core.detection.blink_detector import BOTH, LEFT, RIGHT, BlinkDetector
from app.core.gaze.estimator import GazeReading
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


def test_looking_down_is_not_a_closure():
    # s4 bottom row: both eyes ~0.13, below the 0.18 wink threshold.
    detector = BlinkDetector()
    assert detector.classify(0.13, 0.136) is None
    event, t = _hold(detector, 0.13, 0.136, 0.0, 2.0)
    assert event is None
    assert detector.update(OPEN, OPEN, now=t) is None


def test_wink_registers_while_looking_down():
    detector = BlinkDetector()
    _, t = _hold(detector, 0.04, 0.13, 0.0, 0.5)
    assert detector.update(0.13, 0.13, now=t) == LEFT


def test_slightly_uneven_eyes_are_not_a_wink():
    detector = BlinkDetector()
    _, t = _hold(detector, 0.16, 0.24, 0.0, 0.5)
    assert detector.update(0.24, 0.24, now=t) is None


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


class _ShiftedModel:
    """Predicts the first two feature values, shifted down by ``shift``."""

    def __init__(self, feature_source, shift=0.0, reference_model=None):
        self.feature_source = feature_source
        self.shift = shift
        self.reference_model = reference_model

    def predict(self, features):
        return features[0], features[1] + self.shift


def _frame(t, gaze, primary=True):
    values = (gaze[0], gaze[1], 0.0, 0.0, 0.0, 0.0)
    return GazeReading(face_found=True, features=values, left_ear=OPEN, right_ear=OPEN,
                       captured_at=t, midpoint_features=values,
                       deep_features=values if primary else None)


def _biased_pair():
    # The fallback sits 0.2 screen below the primary, like the ~220 px gap
    # between the pupil and eye-midpoint models in s3.jsonl.
    reference = _ShiftedModel(EYE_MIDPOINT_FEATURE_SOURCE, shift=0.2)
    return _ShiftedModel(GAZEFOLLOWER_FEATURE_SOURCE, reference_model=reference)


def _feed(pipeline, model, frames):
    return [pipeline.process(f, model, output_size=(1000, 1000), now=f.captured_at)
            for f in frames]


def test_brief_primary_dropout_keeps_the_primary_model():
    model, pipeline = _biased_pair(), GazePipeline()
    _feed(pipeline, model, [_frame(1 + i * 0.04, (0.5, 0.5)) for i in range(5)])

    estimate, = _feed(pipeline, model, [_frame(1.24, (0.5, 0.5), primary=False)])

    assert not pipeline.using_reference_model
    assert estimate.raw_y == pytest.approx(500, abs=1)


def test_long_dropout_falls_back_without_jumping():
    model, pipeline = _biased_pair(), GazePipeline()
    _feed(pipeline, model, [_frame(1 + i * 0.04, (0.5, 0.5)) for i in range(10)])

    estimates = _feed(pipeline, model, [_frame(1.4 + i * 0.04, (0.5, 0.5), primary=False)
                                        for i in range(10)])

    assert pipeline.using_reference_model
    # Unaligned, the fallback would put the cursor 200 px lower.
    assert estimates[-1].raw_y == pytest.approx(500, abs=1)
    assert estimates[-1].y == pytest.approx(500, abs=5)
