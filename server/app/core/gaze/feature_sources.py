"""Versioned feature sources for the hybrid calibration and live gaze.

Every camera frame yields several feature vectors (six values; eleven for the
eyeball sources). Calibration fits
one regression per source on the same frames and dots, then keeps whichever
predicts the dots best:

``iris_ring_v1``            iris-ring centre relative to eye corners/lids
``pupil_ellipse_v2``        same geometry from fitted sub-pixel pupil centres
``eye_midpoint_v1``         midpoint between both irises on the eye line; head
                            movement shifts both together and cancels
``eye_midpoint_pupil_v1``   eye-line pointer built from fitted pupil centres
``gazefollower_mgazenet_v1`` GazeFollower's appearance-based network estimate
``nose_eye_v1``             "0 V 0" pyramid: pupil midpoint measured from the
                            nose bridge plus the nose-tip apex direction; no
                            longer a candidate, kept so older profiles still load
``nose_eye_pupil_v1``       the same pyramid built from fitted pupil centres
``eye_geometry_v1``         eye-midpoint offset plus the 3D eye position (cm from
                            the camera) and head pitch; mapped by geometry
                            (core/gaze/geometric_mapper.py), not regression
``eye_geometry_pupil_v1``   the same from fitted pupil centres
``eyeball_v1``              per-eye eyeball rays: each iris offset from its own
                            eye centre, both eye positions and head pose;
                            mapped by core/gaze/eyeball_mapper.py
``eyeball_pupil_v1``        the same from fitted pupil centres

Sources that are not available on every frame (fitted pupils, the network)
carry a landmark reference model that the live pipeline falls back to. The
geometric and eye-midpoint sources are preferred (see calibration.processor).
"""

import math

IRIS_FEATURE_SOURCE = "iris_ring_v1"
PUPIL_FEATURE_SOURCE = "pupil_ellipse_v2"
EYE_MIDPOINT_FEATURE_SOURCE = "eye_midpoint_v1"
EYE_MIDPOINT_PUPIL_FEATURE_SOURCE = "eye_midpoint_pupil_v1"
GAZEFOLLOWER_FEATURE_SOURCE = "gazefollower_mgazenet_v1"
NOSE_EYE_FEATURE_SOURCE = "nose_eye_v1"
NOSE_EYE_PUPIL_FEATURE_SOURCE = "nose_eye_pupil_v1"
EYE_GEOMETRY_FEATURE_SOURCE = "eye_geometry_v1"
EYE_GEOMETRY_PUPIL_FEATURE_SOURCE = "eye_geometry_pupil_v1"
EYEBALL_FEATURE_SOURCE = "eyeball_v1"
EYEBALL_PUPIL_FEATURE_SOURCE = "eyeball_pupil_v1"

CANDIDATE_SOURCES = (
    IRIS_FEATURE_SOURCE,
    PUPIL_FEATURE_SOURCE,
    EYE_MIDPOINT_FEATURE_SOURCE,
    EYE_MIDPOINT_PUPIL_FEATURE_SOURCE,
    GAZEFOLLOWER_FEATURE_SOURCE,
    EYE_GEOMETRY_FEATURE_SOURCE,
    EYE_GEOMETRY_PUPIL_FEATURE_SOURCE,
    EYEBALL_FEATURE_SOURCE,
    EYEBALL_PUPIL_FEATURE_SOURCE,
)
# Fitted in one sitting and used in another (benchmark recordings s1/s2,
# 2026-10-27), eye_midpoint_v1 erred 161-277 px and nose_eye_v1 297-510 px:
# the nose-apex columns tie the mapping to the calibration posture, so the
# nose-eye sources are no longer calibration candidates. The
# geometric source, which adds the 3D eye position and head pitch by
# geometry, did best of all (129 px median, 152 px worst; s1-s3). Per-eye
# eyeball rays beat it cross-sitting on s2-s5 (mean of pairs, 2026-10-29):
# s2<->s3 100 vs 130 px, s4<->s5 246 vs 314, s3<->s4 231 vs 302.
PREFERRED_SOURCES = (
    EYEBALL_FEATURE_SOURCE, EYEBALL_PUPIL_FEATURE_SOURCE,
    EYE_GEOMETRY_FEATURE_SOURCE, EYE_GEOMETRY_PUPIL_FEATURE_SOURCE,
    EYE_MIDPOINT_FEATURE_SOURCE, EYE_MIDPOINT_PUPIL_FEATURE_SOURCE,
)
EYEBALL_SOURCES = frozenset({EYEBALL_FEATURE_SOURCE, EYEBALL_PUPIL_FEATURE_SOURCE})
# Sources mapped by geometry (geometric_mapper / eyeball_mapper) instead of the
# regression; they need the physical screen size.
GEOMETRY_SOURCES = frozenset({EYE_GEOMETRY_FEATURE_SOURCE,
                              EYE_GEOMETRY_PUPIL_FEATURE_SOURCE}) | EYEBALL_SOURCES
# Retired sources still map profiles saved with them.
SUPPORTED_FEATURE_SOURCES = frozenset(CANDIDATE_SOURCES) | {
    NOSE_EYE_FEATURE_SOURCE, NOSE_EYE_PUPIL_FEATURE_SOURCE}

# Sources that can be missing on a frame, and the always-available landmark
# source they fall back to.
REFERENCE_SOURCES = {
    PUPIL_FEATURE_SOURCE: IRIS_FEATURE_SOURCE,
    EYE_MIDPOINT_PUPIL_FEATURE_SOURCE: EYE_MIDPOINT_FEATURE_SOURCE,
    GAZEFOLLOWER_FEATURE_SOURCE: EYE_MIDPOINT_FEATURE_SOURCE,
    NOSE_EYE_PUPIL_FEATURE_SOURCE: NOSE_EYE_FEATURE_SOURCE,
    EYE_GEOMETRY_PUPIL_FEATURE_SOURCE: EYE_GEOMETRY_FEATURE_SOURCE,
    EYEBALL_PUPIL_FEATURE_SOURCE: EYEBALL_FEATURE_SOURCE,
}
FEATURE_LENGTH = 6
EYEBALL_FEATURE_LENGTH = 11
# Sources that need the costly per-frame engines; all others (and every
# reference source) come from MediaPipe landmarks alone.
PUPIL_SOURCES = frozenset({
    PUPIL_FEATURE_SOURCE, EYE_MIDPOINT_PUPIL_FEATURE_SOURCE, NOSE_EYE_PUPIL_FEATURE_SOURCE,
    EYE_GEOMETRY_PUPIL_FEATURE_SOURCE, EYEBALL_PUPIL_FEATURE_SOURCE,
})
DEEP_SOURCES = frozenset({GAZEFOLLOWER_FEATURE_SOURCE})

_READING_FIELDS = {
    IRIS_FEATURE_SOURCE: "features",
    PUPIL_FEATURE_SOURCE: "pupil_features",
    EYE_MIDPOINT_FEATURE_SOURCE: "midpoint_features",
    EYE_MIDPOINT_PUPIL_FEATURE_SOURCE: "pupil_midpoint_features",
    GAZEFOLLOWER_FEATURE_SOURCE: "deep_features",
    NOSE_EYE_FEATURE_SOURCE: "nose_features",
    NOSE_EYE_PUPIL_FEATURE_SOURCE: "pupil_nose_features",
    EYE_GEOMETRY_FEATURE_SOURCE: "geometry_features",
    EYE_GEOMETRY_PUPIL_FEATURE_SOURCE: "pupil_geometry_features",
    EYEBALL_FEATURE_SOURCE: "eyeball_features",
    EYEBALL_PUPIL_FEATURE_SOURCE: "pupil_eyeball_features",
}


def model_feature_source(model) -> str:
    source = getattr(model, "feature_source", IRIS_FEATURE_SOURCE)
    return source if source in SUPPORTED_FEATURE_SOURCES else IRIS_FEATURE_SOURCE


def reference_source(source: str):
    """Fallback source for frames where ``source`` is missing, or ``None``."""
    return REFERENCE_SOURCES.get(source)


def _valid(features, length: int) -> bool:
    try:
        return len(features) == length and all(math.isfinite(float(v)) for v in features)
    except (TypeError, ValueError):
        return False


def features_for_source(reading, source: str):
    """Return a finite feature tuple, or ``None`` when the source is absent."""
    field = _READING_FIELDS.get(source)
    if field is None:
        return None
    features = getattr(reading, field, None)
    length = EYEBALL_FEATURE_LENGTH if source in EYEBALL_SOURCES else FEATURE_LENGTH
    return tuple(float(v) for v in features) if _valid(features, length) else None


def features_for_model(reading, model):
    return features_for_source(reading, model_feature_source(model))


def required_engines(model) -> tuple[bool, bool]:
    """(pupil refinement, deep gaze) needed to feed ``model`` live."""
    source = model_feature_source(model)
    return source in PUPIL_SOURCES, source in DEEP_SOURCES
