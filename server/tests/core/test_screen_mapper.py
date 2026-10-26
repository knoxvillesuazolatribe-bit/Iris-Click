import numpy as np
import pytest

from app.core.calibration.collector import CALIBRATION_POINTS
from app.core.gaze.feature_sources import EYE_MIDPOINT_FEATURE_SOURCE, GAZEFOLLOWER_FEATURE_SOURCE
from app.core.gaze.screen_mapper import CalibrationModel


def _samples(rng, per_point=20, noise=0.002):
    rows = []
    for tx, ty in CALIBRATION_POINTS:
        for _ in range(per_point):
            features = np.array((-0.4 + 0.8 * tx, -0.3 + 0.6 * ty, 0.0, 0.0, 0.02, -0.01))
            rows.append((tuple(features + rng.normal(0, noise, 6)), (tx, ty)))
    return rows


def test_fit_predicts_calibration_targets(rng):
    model = CalibrationModel(feature_source=EYE_MIDPOINT_FEATURE_SOURCE)
    model.fit(_samples(rng))

    x, y = model.predict((-0.4 + 0.8 * 0.71, -0.3 + 0.6 * 0.29, 0.0, 0.0, 0.02, -0.01))

    assert model.rms_error < 0.02
    assert x == pytest.approx(0.71, abs=0.02)
    assert y == pytest.approx(0.29, abs=0.02)


def test_predict_for_screen_scales_fractions_to_pixels(rng):
    model = CalibrationModel(feature_source=EYE_MIDPOINT_FEATURE_SOURCE)
    model.fit(_samples(rng))

    x, y = model.predict_for_screen((0.0, 0.0, 0.0, 0.0, 0.02, -0.01), 1920, 1080)

    assert x == pytest.approx(960, abs=40)
    assert y == pytest.approx(540, abs=25)


def test_round_trip_keeps_predictions_and_reference(rng):
    reference = CalibrationModel(feature_source=EYE_MIDPOINT_FEATURE_SOURCE)
    reference.fit(_samples(rng))
    model = CalibrationModel(feature_source=GAZEFOLLOWER_FEATURE_SOURCE, reference_model=reference)
    model.fit(_samples(rng))
    model.fixation_error = 0.01

    restored = CalibrationModel.from_dict(model.to_dict())

    features = (0.1, 0.05, 0.0, 0.0, 0.02, -0.01)
    assert restored.predict(features) == pytest.approx(model.predict(features))
    assert restored.reference_model.feature_source == EYE_MIDPOINT_FEATURE_SOURCE
    assert restored.accuracy == 0.01


def test_from_dict_rejects_wrong_reference_source(rng):
    reference = CalibrationModel(feature_source=EYE_MIDPOINT_FEATURE_SOURCE)
    reference.fit(_samples(rng))
    payload = reference.to_dict()
    payload["reference_model"] = reference.to_dict()

    assert CalibrationModel.from_dict(payload) is None


def test_fit_rejects_too_few_samples():
    with pytest.raises(ValueError):
        CalibrationModel().fit([((0.5,) * 6, (0.5, 0.5))] * 5)


def _attenuated_samples(rng, per_point=25):
    """Noisy features shrink a least-squares fit toward the screen centre."""
    rows = []
    for tx, ty in CALIBRATION_POINTS:
        for _ in range(per_point):
            features = np.array((-0.4 + 0.8 * tx, -0.3 + 0.6 * ty, 0.0, 0.0, 0.02, -0.01))
            features[:2] += rng.normal(0, 0.12, 2)
            rows.append((tuple(features), (tx, ty)))
    return rows


def _edge_median_x(model, samples, target):
    preds = [model.predict(f)[0] for f, t in samples if t == target]
    return float(np.median(preds))


def test_edge_stretch_reaches_the_screen_edges(rng):
    samples = _attenuated_samples(rng)
    model = CalibrationModel(feature_source=EYE_MIDPOINT_FEATURE_SOURCE)
    model.fit(samples)
    plain = CalibrationModel(feature_source=EYE_MIDPOINT_FEATURE_SOURCE)
    plain.fit(samples)
    plain.edge_stretch = (0.0, 1.0, 0.0, 1.0)

    right_edge = max(x for x, _ in CALIBRATION_POINTS)
    target = (right_edge, 0.5)
    assert model.edge_stretch[1] > 1.0
    assert abs(_edge_median_x(model, samples, target) - right_edge) < \
        abs(_edge_median_x(plain, samples, target) - right_edge)


def test_edge_stretch_never_shrinks_and_round_trips(rng):
    model = CalibrationModel(feature_source=EYE_MIDPOINT_FEATURE_SOURCE)
    model.fit(_samples(rng))
    assert model.edge_stretch[1] >= 1.0 and model.edge_stretch[3] >= 1.0
    restored = CalibrationModel.from_dict(model.to_dict())
    assert restored.edge_stretch == pytest.approx(model.edge_stretch)


def test_profiles_without_edge_stretch_still_load(rng):
    model = CalibrationModel(feature_source=EYE_MIDPOINT_FEATURE_SOURCE)
    model.fit(_samples(rng))
    payload = model.to_dict()
    del payload["edge_stretch"]
    assert CalibrationModel.from_dict(payload).edge_stretch == (0.0, 1.0, 0.0, 1.0)
