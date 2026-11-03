import time
from types import SimpleNamespace

import numpy as np
import pytest

from app.core.calibration import collector as collector_module
from app.core.calibration.collector import (
    CALIBRATION_POINTS,
    CalibrationCollector,
    PointCollector,
    outlier_mask,
)
from app.core.calibration.processor import CalibrationOutcome, fit_hybrid, select_model
from app.core.calibration.profile import load_profile, save_profile
from app.core.gaze.feature_sources import (
    CANDIDATE_SOURCES,
    EYE_MIDPOINT_FEATURE_SOURCE,
    EYE_GEOMETRY_FEATURE_SOURCE,
    EYE_MIDPOINT_PUPIL_FEATURE_SOURCE,
    GAZEFOLLOWER_FEATURE_SOURCE,
    GEOMETRY_SOURCES,
    IRIS_FEATURE_SOURCE,
    NOSE_EYE_FEATURE_SOURCE,
    NOSE_EYE_PUPIL_FEATURE_SOURCE,
    PREFERRED_SOURCES,
    REFERENCE_SOURCES,
    required_engines,
)
from app.schemas.calibration import ScreenSize

from tests.factories import CAMERA_ABOVE_CM, SCREEN_CM, synthetic_reading

GEOMETRY = {"screen_cm": SCREEN_CM, "camera_above_cm": CAMERA_ABOVE_CM}


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

    outcome = fit_hybrid(session.samples, session.point_counts, GEOMETRY)

    assert {source for source, _ in outcome.candidates} == set(CANDIDATE_SOURCES)
    assert outcome.accepted


def test_hybrid_fit_prefers_posture_robust_sources(rng):
    # Synthetic GazeFollower rows map exactly onto the dots, so leave them out
    # to compare engines of similar quality.
    session = _collect_all(rng, deep=False)

    outcome = fit_hybrid(session.samples, session.point_counts, GEOMETRY)

    chosen = outcome.model.feature_source
    assert chosen in PREFERRED_SOURCES
    if chosen in REFERENCE_SOURCES:
        assert outcome.model.reference_model.feature_source == REFERENCE_SOURCES[chosen]


def test_geometric_sources_are_skipped_without_the_screen_size(rng):
    session = _collect_all(rng, deep=False)

    outcome = fit_hybrid(session.samples, session.point_counts)

    assert not {s for s, _ in outcome.candidates} & GEOMETRY_SOURCES


def test_hybrid_fit_skips_sources_missing_at_some_dots(rng):
    session = _collect_all(rng, deep=False, pupils=False)

    outcome = fit_hybrid(session.samples, session.point_counts)

    assert {s for s, _ in outcome.candidates} == {
        IRIS_FEATURE_SOURCE, EYE_MIDPOINT_FEATURE_SOURCE}


def _model(source, error, held_out=None):
    return SimpleNamespace(feature_source=source, accuracy=error, validation_error=held_out)


def test_select_keeps_eye_midpoint_when_others_are_only_slightly_better():
    fitted = {EYE_MIDPOINT_FEATURE_SOURCE: _model(EYE_MIDPOINT_FEATURE_SOURCE, 0.050),
              NOSE_EYE_FEATURE_SOURCE: _model(NOSE_EYE_FEATURE_SOURCE, 0.045)}
    assert select_model(fitted).feature_source == EYE_MIDPOINT_FEATURE_SOURCE


def test_select_switches_when_another_source_is_clearly_better():
    fitted = {EYE_MIDPOINT_FEATURE_SOURCE: _model(EYE_MIDPOINT_FEATURE_SOURCE, 0.080),
              NOSE_EYE_FEATURE_SOURCE: _model(NOSE_EYE_FEATURE_SOURCE, 0.040)}
    assert select_model(fitted).feature_source == NOSE_EYE_FEATURE_SOURCE


def test_select_judges_sources_by_held_out_error():
    # In-sample the nose engine looks far better, but it does not generalise.
    fitted = {EYE_MIDPOINT_FEATURE_SOURCE: _model(EYE_MIDPOINT_FEATURE_SOURCE, 0.060, 0.070),
              NOSE_EYE_FEATURE_SOURCE: _model(NOSE_EYE_FEATURE_SOURCE, 0.030, 0.090)}
    assert select_model(fitted).feature_source == EYE_MIDPOINT_FEATURE_SOURCE


def test_select_prefers_geometric_over_slightly_better_eye_midpoint():
    fitted = {EYE_MIDPOINT_FEATURE_SOURCE: _model(EYE_MIDPOINT_FEATURE_SOURCE, 0.030, 0.100),
              EYE_GEOMETRY_FEATURE_SOURCE: _model(EYE_GEOMETRY_FEATURE_SOURCE, 0.040, 0.120)}
    assert select_model(fitted).feature_source == EYE_GEOMETRY_FEATURE_SOURCE


def test_select_leaves_geometric_when_eye_midpoint_is_clearly_better():
    fitted = {EYE_MIDPOINT_FEATURE_SOURCE: _model(EYE_MIDPOINT_FEATURE_SOURCE, 0.030, 0.060),
              EYE_GEOMETRY_FEATURE_SOURCE: _model(EYE_GEOMETRY_FEATURE_SOURCE, 0.040, 0.120)}
    assert select_model(fitted).feature_source == EYE_MIDPOINT_FEATURE_SOURCE


def test_select_keeps_geometric_past_the_in_sample_limit():
    # Profile 20261101T200151: eye-midpoint 8.9% in-sample but 17.8% held-out.
    fitted = {EYE_MIDPOINT_FEATURE_SOURCE: _model(EYE_MIDPOINT_FEATURE_SOURCE, 0.089, 0.178),
              EYE_GEOMETRY_FEATURE_SOURCE: _model(EYE_GEOMETRY_FEATURE_SOURCE, 0.136, 0.180)}
    assert select_model(fitted).feature_source == EYE_GEOMETRY_FEATURE_SOURCE


def test_select_leaves_a_geometric_source_that_is_clearly_worse_held_out():
    fitted = {EYE_MIDPOINT_FEATURE_SOURCE: _model(EYE_MIDPOINT_FEATURE_SOURCE, 0.089, 0.120),
              EYE_GEOMETRY_FEATURE_SOURCE: _model(EYE_GEOMETRY_FEATURE_SOURCE, 0.200, 0.250)}
    assert select_model(fitted).feature_source == EYE_MIDPOINT_FEATURE_SOURCE


def test_outcome_is_accepted_when_any_source_is_within_the_limit():
    chosen = SimpleNamespace(accuracy=0.136)
    assert CalibrationOutcome(chosen, [(EYE_MIDPOINT_FEATURE_SOURCE, 0.089),
                                       (EYE_GEOMETRY_FEATURE_SOURCE, 0.136)]).accepted
    assert not CalibrationOutcome(chosen, [(EYE_GEOMETRY_FEATURE_SOURCE, 0.136)]).accepted
    assert not CalibrationOutcome(chosen).accepted


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


def test_hybrid_fit_reports_a_held_out_error_per_dot(rng):
    session = _collect_all(rng, deep=False)

    outcome = fit_hybrid(session.samples, session.point_counts)

    model = outcome.model
    assert set(model.held_out_dot_errors) == {tuple(np.round(p, 3)) for p in CALIBRATION_POINTS}
    # A dot the fit never saw is predicted no better than one it did.
    assert model.validation_error >= model.fixation_error


def test_held_out_error_survives_a_profile_round_trip(rng, tmp_path):
    session = _collect_all(rng, deep=False)
    outcome = fit_hybrid(session.samples, session.point_counts)
    save_profile(tmp_path, outcome, "Desk", session.sample_count, None, deep_gaze_available=False)

    _, model = load_profile(tmp_path)

    assert model.validation_error == pytest.approx(outcome.model.validation_error)


@pytest.mark.parametrize(("source", "expected"), [
    (NOSE_EYE_FEATURE_SOURCE, (False, False)),
    (NOSE_EYE_PUPIL_FEATURE_SOURCE, (True, False)),
    (GAZEFOLLOWER_FEATURE_SOURCE, (False, True)),
])
def test_live_tracking_runs_only_the_engines_the_profile_needs(source, expected):
    assert required_engines(SimpleNamespace(feature_source=source)) == expected


def test_per_dot_held_out_errors_survive_a_profile_round_trip(rng, tmp_path):
    session = _collect_all(rng, deep=False)
    outcome = fit_hybrid(session.samples, session.point_counts)
    save_profile(tmp_path, outcome, "Desk", session.sample_count, None, deep_gaze_available=False)

    _, model = load_profile(tmp_path)

    assert len(model.held_out_dot_errors) == len(CALIBRATION_POINTS)
    assert sorted(model.held_out_dot_errors.values()) == pytest.approx(
        sorted(outcome.model.held_out_dot_errors.values()))
