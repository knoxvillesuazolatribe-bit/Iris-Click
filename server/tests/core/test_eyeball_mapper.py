import pytest

from app.core.calibration.collector import CALIBRATION_POINTS
from app.core.detection.iris_detector import eyeball_features as features_from_eye_line
from app.core.gaze.eyeball_mapper import EyeballModel
from app.core.gaze.feature_sources import (
    EYE_GEOMETRY_FEATURE_SOURCE,
    EYEBALL_FEATURE_SOURCE,
    EYEBALL_PUPIL_FEATURE_SOURCE,
    features_for_source,
    required_engines,
)
from app.core.gaze.estimator import GazeReading
from app.core.gaze.screen_mapper import CalibrationModel, ScreenCorrection

from tests.factories import CAMERA_ABOVE_CM, SCREEN_CM, eyeball_features


def _fitted(source=EYEBALL_FEATURE_SOURCE, reference_model=None):
    model = EyeballModel(source, SCREEN_CM, CAMERA_ABOVE_CM, reference_model)
    model.fit([(eyeball_features(p), p) for p in CALIBRATION_POINTS for _ in range(3)])
    return model


def test_fit_maps_calibration_dots_back_to_the_screen():
    model = _fitted()
    for point in ((0.3, 0.7), (0.9, 0.1)):
        assert model.predict(eyeball_features(point)) == pytest.approx(point, abs=0.01)


@pytest.mark.parametrize("eye, yaw, pitch", [
    ((6.0, 8.0, 55.0), 0.0, -0.01),     # slid 6 cm to the side
    ((0.0, 14.0, 55.0), 0.0, -0.01),    # slouched 6 cm lower
    ((0.0, 8.0, 70.0), 0.0, -0.01),     # leaned back 15 cm
    ((0.0, 8.0, 55.0), 0.0, 0.10),      # head tilted ~6 deg
    ((0.0, 8.0, 55.0), 0.12, -0.01),    # head turned ~7 deg
])
def test_posture_change_does_not_move_the_gaze_point(eye, yaw, pitch):
    model = _fitted()
    target = (0.25, 0.4)
    features = eyeball_features(target, eye, yaw, pitch)
    assert model.predict(features) == pytest.approx(target, abs=0.01)


def test_correction_applies_after_the_geometry():
    model = _fitted()
    model.set_correction(ScreenCorrection([1, 0, 0.05, 0, 1, 0]))
    assert model.predict(eyeball_features((0.5, 0.5)))[0] == pytest.approx(0.55, abs=0.01)


def test_round_trip_through_profile_loading():
    model = _fitted(EYEBALL_PUPIL_FEATURE_SOURCE, reference_model=_fitted())
    model.fixation_error = 0.05
    model.yaw_gain = 0.3
    loaded = CalibrationModel.from_dict(model.to_dict())
    assert isinstance(loaded, EyeballModel)
    assert loaded.yaw_gain == 0.3
    assert loaded.reference_model.feature_source == EYEBALL_FEATURE_SOURCE
    features = eyeball_features((0.6, 0.3))
    assert loaded.predict(features) == pytest.approx(model.predict(features))


def test_kind_and_source_must_agree():
    data = _fitted().to_dict()
    data["feature_source"] = EYE_GEOMETRY_FEATURE_SOURCE
    assert CalibrationModel.from_dict(data) is None
    data = _fitted().to_dict()
    del data["yaw_gain"]
    assert CalibrationModel.from_dict(data) is None


def test_pupil_eyeball_needs_pupil_refinement():
    assert required_engines(_fitted(EYEBALL_PUPIL_FEATURE_SOURCE)) == (True, False)
    assert required_engines(_fitted()) == (False, False)


def test_features_are_per_eye_offsets_and_positions_in_cm():
    # 1000x500 frame, focal 900 px; eye centres 90 px apart -> z = 63 cm, 0.07 cm/px.
    eye_line = {"eye_distance": 0.09, "left_eye": (0.545, 0.5), "right_eye": (0.455, 0.5),
                "left_iris": (0.555, 0.5), "right_iris": (0.465, 0.49)}
    features = features_from_eye_line(eye_line, 1000, 500, yaw=0.1, pitch=-0.2)
    assert features == pytest.approx(
        (0.7, 0.0, 0.7, -0.35, 3.15, 0.0, -3.15, 0.0, 63.0, 0.1, -0.2))


def test_fitted_pupils_replace_the_iris_centres():
    eye_line = {"eye_distance": 0.09, "left_eye": (0.545, 0.5), "right_eye": (0.455, 0.5),
                "left_iris": (0.555, 0.5), "right_iris": (0.465, 0.49)}
    features = features_from_eye_line(eye_line, 1000, 500, 0.0, 0.0,
                                      iris_centres=((545.0, 250.0), (455.0, 250.0)))
    assert features[:4] == pytest.approx((0.0, 0.0, 0.0, 0.0))


def test_source_lookup_checks_the_eleven_value_length():
    reading = GazeReading(face_found=True, eyeball_features=eyeball_features((0.5, 0.5)))
    assert len(features_for_source(reading, EYEBALL_FEATURE_SOURCE)) == 11
    reading.eyeball_features = (0.0,) * 6
    assert features_for_source(reading, EYEBALL_FEATURE_SOURCE) is None
