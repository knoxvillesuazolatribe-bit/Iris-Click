import numpy as np
import pytest

from app.core.calibration.recenter import (
    COLLECT_S,
    LEAD_IN_S,
    MAX_DOT_S,
    RECENTER_POINTS,
    SETTLE_S,
    RecenterSession,
    fit_correction,
    load_recenter,
    save_recenter,
)
from app.core.gaze.screen_mapper import CalibrationModel, ScreenCorrection

FRAME_S = 1 / 25
# The identity ridge trades ~0.01 (~20 px) of bias on an exact drift for
# stable fits on noisy webcam dots.
FIT_TOLERANCE = 0.02


def _drifted(x, y):
    """Today's posture: everything 6% too low and squeezed 15% horizontally."""
    return 0.5 + (x - 0.5) * 0.85, y + 0.06


def _run_session(gaze, start=0.0):
    session, t = RecenterSession(start), start
    while not session.finished and t < start + 30:
        target = session.target
        session.update(t, gaze(*target) if target else None)
        t += FRAME_S
    return session


def test_fit_correction_undoes_a_shift_and_squeeze():
    pairs = [(_drifted(*p), p) for p in RECENTER_POINTS]
    correction, residual = fit_correction(pairs)
    assert residual < FIT_TOLERANCE
    for x, y in ((0.3, 0.7), (0.75, 0.2)):
        assert correction.apply(*_drifted(x, y)) == pytest.approx((x, y), abs=FIT_TOLERANCE)


def test_fit_correction_rejects_dots_the_user_did_not_follow():
    pairs = [((0.5, 0.5), p) for p in RECENTER_POINTS]
    with pytest.raises(ValueError):
        fit_correction(pairs)


def test_fit_correction_rejects_looks_unrelated_to_the_dots():
    rng = np.random.default_rng(3)
    for _ in range(5):
        pairs = [(tuple(rng.uniform(0.3, 0.7, 2)), p) for p in RECENTER_POINTS]
        with pytest.raises(ValueError):
            fit_correction(pairs)


def test_fit_correction_accepts_typical_webcam_noise():
    # Real re-centres on s2-s5 left an RMS residual of 0.12-0.18 on the dots.
    rng = np.random.default_rng(4)
    pairs = [(tuple(np.array(_drifted(*p)) + rng.normal(0, 0.08, 2)), p)
             for p in RECENTER_POINTS]
    correction, _ = fit_correction(pairs)
    assert correction is not None


def test_session_steps_through_every_dot_and_fits():
    session = _run_session(_drifted)
    assert session.error is None
    correction, residual = session.result()
    assert correction.apply(*_drifted(0.2, 0.4)) == pytest.approx((0.2, 0.4), abs=FIT_TOLERANCE)
    assert residual < FIT_TOLERANCE


def test_session_ignores_samples_while_the_eyes_travel_to_the_dot():
    session = RecenterSession(0.0)
    session.update(0.1, (0.99, 0.99))
    assert session.progress(0.1) == 0.0
    assert session.progress(LEAD_IN_S + SETTLE_S) == 0.0
    assert session.progress(LEAD_IN_S + SETTLE_S + COLLECT_S) == 1.0


def test_session_fails_when_the_eyes_stay_closed():
    session = RecenterSession(0.0)
    t = 0.0
    while t <= LEAD_IN_S + MAX_DOT_S + FRAME_S:
        session.update(t, None)
        t += FRAME_S
    assert session.finished and "dot 1 of 5" in session.error
    with pytest.raises(ValueError):
        session.result()


def test_correction_applies_to_the_model_and_its_fallback():
    model = CalibrationModel(feature_source="eye_midpoint_pupil_v1",
                             reference_model=CalibrationModel(feature_source="eye_midpoint_v1"))
    shift = ScreenCorrection([1, 0, 0.1, 0, 1, -0.05])
    model.set_correction(shift)
    assert model.reference_model.correction is shift
    model.set_correction(None)
    assert model.reference_model.correction is None


def test_saved_recenter_is_only_used_for_its_own_profile(tmp_path):
    path = tmp_path / "recenter.json"
    save_recenter(path, "profile-a", ScreenCorrection([1, 0, 0.02, 0, 1, -0.03]), 0.01)
    loaded = load_recenter(path, "profile-a")
    assert loaded.apply(0.5, 0.5) == pytest.approx((0.52, 0.47))
    assert load_recenter(path, "profile-b") is None
    assert load_recenter(tmp_path / "missing.json", "profile-a") is None
    path.write_text("{not json", encoding="utf-8")
    assert load_recenter(path, "profile-a") is None


def test_time_without_frames_does_not_count_against_a_dot():
    # The worker delivered nothing for 5 s (e.g. the physical mouse was used).
    session = RecenterSession(0.0)
    session.update(0.0, None)
    t = 5.0
    while not session.finished and t < 40:
        target = session.target
        session.update(t, _drifted(*target) if target else None)
        t += FRAME_S
    assert session.error is None
    assert session.result()[1] < FIT_TOLERANCE
