import time
from types import SimpleNamespace

import pytest

from app.core.calibration import collector as collector_module
from app.core.calibration.collector import (
    CALIBRATION_POINTS,
    CalibrationCollector,
    PointCollector,
    outlier_mask,
)
from app.core.calibration.processor import fit_hybrid, select_model
from app.core.calibration.profile import load_profile, save_profile
from app.core.gaze.feature_sources import (
    CANDIDATE_SOURCES,
    EYE_MIDPOINT_FEATURE_SOURCE,
    GAZEFOLLOWER_FEATURE_SOURCE,
    IRIS_FEATURE_SOURCE,
    NOSE_EYE_FEATURE_SOURCE,
    NOSE_EYE_PUPIL_FEATURE_SOURCE,
    PREFERRED_SOURCES,
)
from app.schemas.calibration import ScreenSize

from tests.factories import synthetic_reading


def _collect_all(rng, **reading_kwargs):
    session = CalibrationCollector()
    for target in CALIBRATION_POINTS:
        point = PointCollector(target, started_at=time.perf_counter() - 1)
        for _ in range(25):
            point.observe(synthetic_reading(target, rng, **reading_kwargs))
        assert point.has_enough()
        session.add_point(point)
    return session


def test_outlier_mask_drops_far_sample():
    rows = [(0.5, 0.5, 0, 0, 0, 0)] * 10 + [(0.9, 0.1, 0, 0, 0, 0)]
    assert outlier_mask(rows) == [True] * 10 + [False]


def test_point_collector_ignores_frames_before_start_and_closed_eyes(rng):
    point = PointCollector((0.5, 0.5), started_at=time.perf_counter() + 60)
    assert not point.observe(synthetic_reading((0.5, 0.5), rng))

    point = PointCollector((0.5, 0.5), started_at=time.perf_counter() - 1)
    assert not point.observe(synthetic_reading((0.5, 0.5), rng, left_ear=0.02, right_ear=0.02))
    assert point.reason == "eyes_closed"


def test_point_collector_extends_until_enough_samples(rng, monkeypatch):
    monkeypatch.setattr(collector_module, "MIN_SAMPLES_PER_POINT", 5)
    point = PointCollector((0.5, 0.5), started_at=time.perf_counter() - 1)
    for _ in range(3):
        point.observe(synthetic_reading((0.5, 0.5), rng))

    assert not point.is_finished(collector_module.COLLECT_MS)
    assert point.is_finished(collector_module.MAX_COLLECT_MS)


def test_hybrid_fit_fits_every_source(rng):
    session = _collect_all(rng)

    outcome = fit_hybrid(session.samples, session.point_counts)

    assert {source for source, _ in outcome.candidates} == set(CANDIDATE_SOURCES)
    assert outcome.accepted


def test_hybrid_fit_prefers_nose_eye_over_similar_sources(rng):
    # Synthetic GazeFollower rows map exactly onto the dots, so leave them out
    # to compare engines of similar quality.
    session = _collect_all(rng, deep=False)

    outcome = fit_hybrid(session.samples, session.point_counts)

    assert outcome.model.feature_source in PREFERRED_SOURCES
    if outcome.model.feature_source == NOSE_EYE_PUPIL_FEATURE_SOURCE:
        assert outcome.model.reference_model.feature_source == NOSE_EYE_FEATURE_SOURCE


def test_hybrid_fit_skips_sources_missing_at_some_dots(rng):
    session = _collect_all(rng, deep=False, pupils=False)

    outcome = fit_hybrid(session.samples, session.point_counts)

    assert {s for s, _ in outcome.candidates} == {
        IRIS_FEATURE_SOURCE, EYE_MIDPOINT_FEATURE_SOURCE, NOSE_EYE_FEATURE_SOURCE}


def _model(source, error):
    return SimpleNamespace(feature_source=source, accuracy=error)


def test_select_keeps_nose_eye_when_others_are_only_slightly_better():
    fitted = {NOSE_EYE_FEATURE_SOURCE: _model(NOSE_EYE_FEATURE_SOURCE, 0.050),
              GAZEFOLLOWER_FEATURE_SOURCE: _model(GAZEFOLLOWER_FEATURE_SOURCE, 0.045)}
    assert select_model(fitted).feature_source == NOSE_EYE_FEATURE_SOURCE


def test_select_switches_when_another_source_is_clearly_better():
    fitted = {NOSE_EYE_FEATURE_SOURCE: _model(NOSE_EYE_FEATURE_SOURCE, 0.080),
              EYE_MIDPOINT_FEATURE_SOURCE: _model(EYE_MIDPOINT_FEATURE_SOURCE, 0.040)}
    assert select_model(fitted).feature_source == EYE_MIDPOINT_FEATURE_SOURCE


def test_profile_round_trip(rng, tmp_path):
    session = _collect_all(rng)
    outcome = fit_hybrid(session.samples, session.point_counts)

    saved = save_profile(tmp_path, outcome, "Desk", session.sample_count,
                         ScreenSize(width=1920, height=1080), deep_gaze_available=True)
    profile, model = load_profile(tmp_path)

    assert profile.id == saved.id
    assert model.feature_source == outcome.model.feature_source
    features = synthetic_reading((0.3, 0.6), rng).features
    if model.feature_source == IRIS_FEATURE_SOURCE:
        assert model.predict(features) == pytest.approx(outcome.model.predict(features))


def test_load_profile_rejects_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        load_profile(tmp_path, "../../secrets")


def test_calibration_covers_screen_edges():
    xs = [x for x, _ in CALIBRATION_POINTS]
    ys = [y for _, y in CALIBRATION_POINTS]
    assert min(xs) <= 0.05 and max(xs) >= 0.95
    assert min(ys) <= 0.05 and max(ys) >= 0.95
