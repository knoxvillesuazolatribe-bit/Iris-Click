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
    EYEBALL_SOURCES,
    GEOMETRY_SOURCES,
    PREFERRED_SOURCES,
    REFERENCE_SOURCES,
)
from app.core.gaze.eyeball_mapper import EyeballModel
from app.core.gaze.geometric_mapper import GeometricModel
from app.core.gaze.screen_mapper import CalibrationModel

# Accepted below the first limit; accepted with a low-accuracy warning (large
# targets still work) up to the second; rejected above it. Screen fractions.
MAX_FIT_ERROR_FRACTION = 0.06
MAX_LOW_ACCURACY_FRACTION = 0.10
# A source must have at least this many samples at every dot to compete.
MIN_SOURCE_SAMPLES_PER_POINT = 5
# A non-preferred source must beat the preferred engine's selection error by
# this fraction AND by this absolute screen fraction (~19 px at 1920 wide) to be
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


def new_model(source: str, geometry: dict | None = None):
    """An unfitted model for ``source``; geometric sources need ``geometry``
    (GeometricModel keyword arguments: screen_cm, camera_above_cm)."""
    if source in EYEBALL_SOURCES:
        return EyeballModel(source, **(geometry or {}))
    if source in GEOMETRY_SOURCES:
        return GeometricModel(source, **(geometry or {}))
    return CalibrationModel(feature_source=source)


def held_out_dot_errors(source: str, samples,
                        geometry: dict | None = None) -> dict[tuple, float] | None:
    """Per-dot error (screen fraction) of a fit made without that dot.

    Edge dots become extrapolation when held out, so this is pessimistic at
    the border and honest in the interior; ``None`` when a fold cannot fit.
    """
    groups: dict[tuple, list] = {}
    for features, target in samples:
        groups.setdefault(tuple(np.round(target, 3)), []).append(features)
    errors = {}
    for dot, held_out in groups.items():
        model = new_model(source, geometry)
        try:
            model.fit([s for s in samples if tuple(np.round(s[1], 3)) != dot])
            predicted = np.median([model.predict(f) for f in held_out], axis=0)
        except (ValueError, np.linalg.LinAlgError):
            return None
        errors[dot] = float(np.hypot(*(predicted - np.asarray(dot))))
    return errors


def _rms(values) -> float:
    return float(np.sqrt(np.mean(np.square(list(values)))))


@dataclass
class CalibrationOutcome:
    model: CalibrationModel
    candidates: list[tuple[str, float]] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return float(self.model.accuracy)

    @property
    def accepted(self) -> bool:
        """Judges the session by its best source: the chosen one may be a
        geometric source with a higher in-sample error (see select_model)."""
        best = min((error for _, error in self.candidates), default=self.accuracy)
        return best <= MAX_LOW_ACCURACY_FRACTION

    @property
    def low_accuracy(self) -> bool:
        return self.accuracy > MAX_FIT_ERROR_FRACTION


def _fit_source(source, samples, geometry: dict | None = None):
    model = new_model(source, geometry)
    try:
        model.fit(samples)
        model.fixation_error = fixation_error(model, samples)
    except (ValueError, np.linalg.LinAlgError) as exc:
        logger.warning("%s fit failed: %s", source, exc)
        return None
    if not np.isfinite(model.accuracy):
        return None
    dot_errors = held_out_dot_errors(source, samples, geometry)
    if dot_errors:
        model.validation_error = _rms(dot_errors.values())
        model.held_out_dot_errors = dot_errors
    return model


def selection_error(model) -> float:
    """Held-out per-dot error when known: in-sample error rewards sources that
    nearly memorise 13 dots with 12 coefficients per axis."""
    held_out = getattr(model, "validation_error", None)
    return held_out if held_out is not None else model.accuracy


def select_model(fitted: dict[str, CalibrationModel]) -> CalibrationModel:
    """Geometric engines first, then eye-midpoint; another source replaces the
    preferred one only when clearly more accurate.

    Only the geometric mapping survives a distance change once re-centred
    (benchmark s4<->s5, 40 vs 64 cm: 170-190 px vs 410-640 px for eye-midpoint),
    at a small within-sitting cost (s2-s5: 105-247 px vs 113-199 px).

    The in-sample limit only restricts which non-preferred source may win. It
    must not remove preferred ones: 12 coefficients nearly memorise 13 dots
    (profile 20261101T200151: eye-midpoint 8.9% in-sample, 17.8% held-out), so
    the limit dropped the geometric sources at 11-14% before they could compete.
    """
    acceptable = {s: m for s, m in fitted.items() if m.accuracy <= MAX_LOW_ACCURACY_FRACTION}
    overall = min((acceptable or fitted).values(), key=selection_error)
    geometric = [fitted[s] for s in PREFERRED_SOURCES if s in fitted and s in GEOMETRY_SOURCES]
    preferred = geometric or [fitted[s] for s in PREFERRED_SOURCES if s in fitted]
    if not preferred:
        return overall
    best_preferred = min(preferred, key=selection_error)
    best, chosen = selection_error(overall), selection_error(best_preferred)
    if (chosen - best > PREFERRED_SOURCE_MIN_GAIN
            and best < chosen * (1.0 - PREFERRED_SOURCE_MARGIN)):
        return overall
    return best_preferred


def fit_hybrid(samples: dict[str, list], point_counts: dict[str, list[int]],
               geometry: dict | None = None) -> CalibrationOutcome:
    """Fit every covered source and return the best; raise ValueError if none fit.

    ``geometry`` (screen_cm, camera_above_cm) enables the geometric sources;
    without the physical screen size they are skipped.
    """
    fitted: dict[str, CalibrationModel] = {}
    # Landmark references first: the other sources depend on them.
    ordered = sorted(CANDIDATE_SOURCES, key=lambda s: s in REFERENCE_SOURCES)
    for source in ordered:
        counts = point_counts.get(source, [])
        if not counts or min(counts) < MIN_SOURCE_SAMPLES_PER_POINT:
            logger.info("Calibration candidate %s skipped (per-dot samples: %s)", source, counts)
            continue
        if source in GEOMETRY_SOURCES and geometry is None:
            continue
        reference_name = REFERENCE_SOURCES.get(source)
        if reference_name is not None and reference_name not in fitted:
            continue
        model = _fit_source(source, samples[source], geometry)
        if model is None:
            continue
        if reference_name is not None:
            model.reference_model = fitted[reference_name]
        fitted[source] = model
        logger.info("Calibration candidate %s: per-dot error=%.4f, held-out=%s, rms=%.4f, "
                    "edge stretch x%.2f y%.2f",
                    source, model.accuracy,
                    "n/a" if model.validation_error is None else f"{model.validation_error:.4f}",
                    model.rms_error, model.edge_stretch[1], model.edge_stretch[3])

    if not fitted:
        raise ValueError("No eye-tracking source could be fitted to the calibration dots.")
    best = select_model(fitted)
    logger.info("Calibration using %s (per-dot error=%.4f)", best.feature_source, best.accuracy)
    dot_errors = best.held_out_dot_errors
    if dot_errors:
        # Shows which screen regions the mapping extrapolates badly.
        logger.info("Held-out error by dot (x, y): %s", ", ".join(
            f"({x:.2f},{y:.2f})={e:.3f}" for (x, y), e in sorted(dot_errors.items())))
    return CalibrationOutcome(
        model=best,
        candidates=sorted(((s, m.accuracy) for s, m in fitted.items()), key=lambda c: c[1]),
    )
