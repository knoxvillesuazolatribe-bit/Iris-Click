import pytest

from app.core.calibration.collector import CALIBRATION_POINTS
from app.core.gaze.feature_sources import (
    EYE_GEOMETRY_FEATURE_SOURCE,
    EYE_GEOMETRY_PUPIL_FEATURE_SOURCE,
    required_engines,
)
from app.core.gaze.geometric_mapper import GeometricModel
from app.core.gaze.screen_mapper import CalibrationModel, ScreenCorrection

from tests.factories import CAMERA_ABOVE_CM, SCREEN_CM, geometry_features


def _fitted(source=EYE_GEOMETRY_FEATURE_SOURCE, reference_model=None):
    model = GeometricModel(source, SCREEN_CM, CAMERA_ABOVE_CM, reference_model)
    model.fit([(geometry_features(p), p) for p in CALIBRATION_POINTS for _ in range(3)])
    return model


def test_fit_maps_calibration_dots_back_to_the_screen():
    model = _fitted()
    for point in ((0.3, 0.7), (0.9, 0.1)):
        assert model.predict(geometry_features(point)) == pytest.approx(point, abs=0.01)


@pytest.mark.parametrize("eye, pitch", [
    ((6.0, 8.0, 55.0), -0.01),    # slid 6 cm to the side
    ((0.0, 14.0, 55.0), -0.01),   # slouched 6 cm lower
    ((0.0, 8.0, 70.0), -0.01),    # leaned back 15 cm
    ((0.0, 8.0, 55.0), 0.10),     # head tilted ~6 deg
])
def test_posture_change_does_not_move_the_gaze_point(eye, pitch):
    # Calibrated sitting at (0, 8, 55) cm; the eyes still look at the same dot.
    model = _fitted()
    target = (0.25, 0.4)
    assert model.predict(geometry_features(target, eye, pitch)) == pytest.approx(target, abs=0.01)


def test_correction_applies_after_the_geometry():
    model = _fitted()
    model.set_correction(ScreenCorrection([1, 0, 0.05, 0, 1, 0]))
    assert model.predict(geometry_features((0.5, 0.5)))[0] == pytest.approx(0.55, abs=0.01)


def test_round_trip_through_profile_loading():
    model = _fitted(EYE_GEOMETRY_PUPIL_FEATURE_SOURCE, reference_model=_fitted())
    model.fixation_error = 0.05
    loaded = CalibrationModel.from_dict(model.to_dict())
    assert isinstance(loaded, GeometricModel)
    assert loaded.reference_model.feature_source == EYE_GEOMETRY_FEATURE_SOURCE
    features = geometry_features((0.6, 0.3))
    assert loaded.predict(features) == pytest.approx(model.predict(features))


def test_mismatched_reference_or_version_is_rejected():
    data = _fitted(EYE_GEOMETRY_PUPIL_FEATURE_SOURCE, reference_model=_fitted()).to_dict()
    data["reference_model"]["feature_source"] = "iris_ring_v1"
    assert CalibrationModel.from_dict(data) is None
    data = _fitted().to_dict()
    data["geometry_version"] = 99
    assert CalibrationModel.from_dict(data) is None


def test_pupil_geometry_needs_pupil_refinement():
    model = _fitted(EYE_GEOMETRY_PUPIL_FEATURE_SOURCE)
    assert required_engines(model) == (True, False)
    assert required_engines(_fitted()) == (False, False)
