"""Hybrid fit: one regression per feature source, keep the most accurate.

The landmark engine (iris ring, fitted pupils, eye-line midpoint) and the
GazeFollower network are fitted on the same frames and dots. Sources that can
be missing on a frame carry their landmark reference model so the live
pipeline can fall back frame by frame.
"""

import logging
from dataclasses import dataclass, field

import numpy as np

from app.core.gaze.feature_sources import (
    CANDIDATE_SOURCES,
    PREFERRED_SOURCES,
    REFERENCE_SOURCES,
)
from app.core.gaze.screen_mapper import CalibrationModel

# Accepted below the first limit; accepted with a low-accuracy warning (large
# targets still work) up to the second; rejected above it. Screen fractions.
MAX_FIT_ERROR_FRACTION = 0.06
MAX_LOW_ACCURACY_FRACTION = 0.10
# A source must have at least this many samples at every dot to compete.
MIN_SOURCE_SAMPLES_PER_POINT = 5
# A non-preferred source must beat the nose-eye engine's per-dot error by this
# fraction AND by this absolute screen fraction (~19 px at 1920 wide) to be
# chosen; smaller gaps are within dot-to-dot noise.
PREFERRED_SOURCE_MARGIN = 0.25
PREFERRED_SOURCE_MIN_GAIN = 0.01

logger = logging.getLogger("irisclick.calibration")


def fixation_error(model: CalibrationModel, samples) -> float:
    """RMS error of each dot's median prediction, as a screen fraction."""
    targets = np.asarray([target for _, target in samples], dtype=float)
    predicted = np.asarray([model.predict(features) for features, _ in samples], dtype=float)
    groups: dict[tuple, list[int]] = {}
    for index, target in enumerate(map(tuple, targets)):
        groups.setdefault(target, []).append(index)
    errors = [np.median(predicted[idx], axis=0) - targets[idx[0]] for idx in groups.values()]
    return float(np.sqrt(np.mean(np.sum(np.asarray(errors) ** 2, axis=1))))


@dataclass
class CalibrationOutcome:
    model: CalibrationModel
    candidates: list[tuple[str, float]] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return float(self.model.accuracy)

    @property
    def accepted(self) -> bool:
        return self.accuracy <= MAX_LOW_ACCURACY_FRACTION

    @property
    def low_accuracy(self) -> bool:
        return self.accuracy > MAX_FIT_ERROR_FRACTION


def _fit_source(source, samples) -> CalibrationModel | None:
    model = CalibrationModel(feature_source=source)
    try:
        model.fit(samples)
        model.fixation_error = fixation_error(model, samples)
    except (ValueError, np.linalg.LinAlgError) as exc:
        logger.warning("%s fit failed: %s", source, exc)
        return None
    if not np.isfinite(model.accuracy):
        return None
    return model


def select_model(fitted: dict[str, CalibrationModel]) -> CalibrationModel:
    """The nose-anchored "0 V 0" engine is the design basis; another source
    replaces it only when it is clearly more accurate on the same dots."""
    overall = min(fitted.values(), key=lambda m: m.accuracy)
    preferred = [fitted[s] for s in PREFERRED_SOURCES if s in fitted]
    if not preferred:
        return overall
    best_preferred = min(preferred, key=lambda m: m.accuracy)
    gain = best_preferred.accuracy - overall.accuracy
    if (gain > PREFERRED_SOURCE_MIN_GAIN
            and overall.accuracy < best_preferred.accuracy * (1.0 - PREFERRED_SOURCE_MARGIN)):
        return overall
    return best_preferred


def fit_hybrid(samples: dict[str, list], point_counts: dict[str, list[int]]) -> CalibrationOutcome:
    """Fit every covered source and return the best; raise ValueError if none fit."""
    fitted: dict[str, CalibrationModel] = {}
    # Landmark references first: the other sources depend on them.
    ordered = sorted(CANDIDATE_SOURCES, key=lambda s: s in REFERENCE_SOURCES)
    for source in ordered:
        counts = point_counts.get(source, [])
        if not counts or min(counts) < MIN_SOURCE_SAMPLES_PER_POINT:
            logger.info("Calibration candidate %s skipped (per-dot samples: %s)", source, counts)
            continue
        reference_name = REFERENCE_SOURCES.get(source)
        if reference_name is not None and reference_name not in fitted:
            continue
        model = _fit_source(source, samples[source])
        if model is None:
            continue
        if reference_name is not None:
            model.reference_model = fitted[reference_name]
        fitted[source] = model
        logger.info("Calibration candidate %s: per-dot error=%.4f, rms=%.4f, edge stretch x%.2f y%.2f",
                    source, model.accuracy, model.rms_error,
                    model.edge_stretch[1], model.edge_stretch[3])

    if not fitted:
        raise ValueError("No eye-tracking source could be fitted to the calibration dots.")
    best = select_model(fitted)
    logger.info("Calibration using %s (per-dot error=%.4f)", best.feature_source, best.accuracy)
    return CalibrationOutcome(
        model=best,
        candidates=sorted(((s, m.accuracy) for s, m in fitted.items()), key=lambda c: c[1]),
    )
