"""Versioned feature sources for the hybrid calibration and live gaze.

Every camera frame yields several six-value feature vectors. Calibration fits
one regression per source on the same frames and dots, then keeps whichever
predicts the dots best:

``iris_ring_v1``            iris-ring centre relative to eye corners/lids
``pupil_ellipse_v2``        same geometry from fitted sub-pixel pupil centres
``eye_midpoint_v1``         midpoint between both irises on the eye line; head
                            movement shifts both together and cancels
``eye_midpoint_pupil_v1``   eye-line pointer built from fitted pupil centres
``gazefollower_mgazenet_v1`` GazeFollower's appearance-based network estimate
``nose_eye_v1``             "0 V 0" pyramid: pupil midpoint measured from the
                            nose bridge (eyes drive it) plus the nose-tip apex
                            direction (head); see iris_detector.nose_eye_pointer
``nose_eye_pupil_v1``       the same pyramid built from fitted pupil centres

Sources that are not available on every frame (fitted pupils, the network)
carry a landmark reference model that the live pipeline falls back to. The
nose-eye sources are the preferred engine (see calibration.processor).
"""

import math

IRIS_FEATURE_SOURCE = "iris_ring_v1"
PUPIL_FEATURE_SOURCE = "pupil_ellipse_v2"
EYE_MIDPOINT_FEATURE_SOURCE = "eye_midpoint_v1"
EYE_MIDPOINT_PUPIL_FEATURE_SOURCE = "eye_midpoint_pupil_v1"
GAZEFOLLOWER_FEATURE_SOURCE = "gazefollower_mgazenet_v1"
NOSE_EYE_FEATURE_SOURCE = "nose_eye_v1"
NOSE_EYE_PUPIL_FEATURE_SOURCE = "nose_eye_pupil_v1"

CANDIDATE_SOURCES = (
    IRIS_FEATURE_SOURCE,
    PUPIL_FEATURE_SOURCE,
    EYE_MIDPOINT_FEATURE_SOURCE,
    EYE_MIDPOINT_PUPIL_FEATURE_SOURCE,
    GAZEFOLLOWER_FEATURE_SOURCE,
    NOSE_EYE_FEATURE_SOURCE,
    NOSE_EYE_PUPIL_FEATURE_SOURCE,
)
PREFERRED_SOURCES = (NOSE_EYE_PUPIL_FEATURE_SOURCE, NOSE_EYE_FEATURE_SOURCE)
SUPPORTED_FEATURE_SOURCES = frozenset(CANDIDATE_SOURCES)

# Sources that can be missing on a frame, and the always-available landmark
# source they fall back to.
REFERENCE_SOURCES = {
    PUPIL_FEATURE_SOURCE: IRIS_FEATURE_SOURCE,
    EYE_MIDPOINT_PUPIL_FEATURE_SOURCE: EYE_MIDPOINT_FEATURE_SOURCE,
    GAZEFOLLOWER_FEATURE_SOURCE: EYE_MIDPOINT_FEATURE_SOURCE,
    NOSE_EYE_PUPIL_FEATURE_SOURCE: NOSE_EYE_FEATURE_SOURCE,
}
FEATURE_LENGTH = 6

_READING_FIELDS = {
    IRIS_FEATURE_SOURCE: "features",
    PUPIL_FEATURE_SOURCE: "pupil_features",
    EYE_MIDPOINT_FEATURE_SOURCE: "midpoint_features",
    EYE_MIDPOINT_PUPIL_FEATURE_SOURCE: "pupil_midpoint_features",
    GAZEFOLLOWER_FEATURE_SOURCE: "deep_features",
    NOSE_EYE_FEATURE_SOURCE: "nose_features",
    NOSE_EYE_PUPIL_FEATURE_SOURCE: "pupil_nose_features",
}


def model_feature_source(model) -> str:
    source = getattr(model, "feature_source", IRIS_FEATURE_SOURCE)
    return source if source in SUPPORTED_FEATURE_SOURCES else IRIS_FEATURE_SOURCE


def reference_source(source: str):
    """Fallback source for frames where ``source`` is missing, or ``None``."""
    return REFERENCE_SOURCES.get(source)


def _valid(features) -> bool:
    try:
        return len(features) == FEATURE_LENGTH and all(math.isfinite(float(v)) for v in features)
    except (TypeError, ValueError):
        return False


def features_for_source(reading, source: str):
    """Return a finite six-value tuple, or ``None`` when the source is absent."""
    field = _READING_FIELDS.get(source)
    if field is None:
        return None
    features = getattr(reading, field, None)
    return tuple(float(v) for v in features) if _valid(features) else None


def features_for_model(reading, model):
    return features_for_source(reading, model_feature_source(model))
