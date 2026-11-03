"""Quick re-centre: five dots that correct the calibration for today's posture.

Recorded sessions showed the calibrated mapping shifting and scaling after the
user sat differently; a fixed offset alone fixed little, while an affine fit
on five dots roughly halved the error. The regression itself is untouched.

Coordinates are screen fractions (0..1); ``now`` is any monotonic clock in s.
"""

import logging
import math
from datetime import datetime
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from app.core.gaze.screen_mapper import ScreenCorrection
from app.schemas.calibration import PostureReference, RecenterFile

logger = logging.getLogger("irisclick.recenter")

# Centre first, then the corners at the benchmark grid's outer ring.
RECENTER_POINTS = ((0.50, 0.50), (0.08, 0.08), (0.92, 0.08), (0.92, 0.92), (0.08, 0.92))
# Time to look away from the button that started the re-centre.
LEAD_IN_S = 1.0
# The eyes need ~0.5 s to land and settle after a dot appears.
SETTLE_S = 0.7
COLLECT_S = 0.9
# A dot without this many open-eye frames by MAX_DOT_S fails the session.
MIN_SAMPLES = 8
MAX_DOT_S = 3.0
# A longer gap between updates means the worker was not delivering frames
# (physical mouse, camera hiccup); that time does not count against the dot.
STALL_S = 0.3
# Pulls the 6 affine parameters toward "no change": 5 dots barely determine
# them, and a noisy dot must not shear the whole screen. 0.1 scored best
# with compare_estimators.py on s2-s5 (geometric: 117 px vs 121 at 0.02).
IDENTITY_RIDGE = 0.1
# Limits only catch a user who did not look at the dots. Real re-centres on
# s2-s5 needed gains 0.71-1.51, shear up to 0.48 and left an RMS residual of
# 0.12-0.18 (per-target webcam error), so the old 0.6-1.7 / 0.35 / 0.06
# limits refused every one of them and the cross-sitting error stayed 270 px.
GAIN_RANGE = (0.5, 2.2)
MAX_SHEAR = 0.6
MAX_RESIDUAL = 0.2


def fit_correction(pairs) -> tuple[ScreenCorrection, float]:
    """Fit predicted -> target over ((px, py), (tx, ty)) pairs.

    Returns (correction, RMS residual) or raises ValueError for an implausible
    fit (degenerate points, extreme gains/shear, or a large residual).
    """
    if len(pairs) < 3:
        raise ValueError("Not enough re-centre dots.")
    predicted = np.array([p for p, _ in pairs], dtype=float)
    targets = np.array([t for _, t in pairs], dtype=float)
    design = np.column_stack([predicted, np.ones(len(predicted))])
    identity = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    lhs = design.T @ design + IDENTITY_RIDGE * np.eye(3)
    try:
        matrix = np.vstack([np.linalg.solve(lhs, design.T @ targets[:, axis]
                                            + IDENTITY_RIDGE * identity[axis])
                            for axis in (0, 1)])
    except np.linalg.LinAlgError as exc:
        raise ValueError("Re-centre dots are degenerate.") from exc
    if not np.all(np.isfinite(matrix)):
        raise ValueError("Re-centre fit is not finite.")
    low, high = GAIN_RANGE
    if not (low <= matrix[0, 0] <= high and low <= matrix[1, 1] <= high):
        raise ValueError("Re-centre would rescale the screen implausibly.")
    if abs(matrix[0, 1]) > MAX_SHEAR or abs(matrix[1, 0]) > MAX_SHEAR:
        raise ValueError("Re-centre would skew the screen implausibly.")
    correction = ScreenCorrection(matrix)
    corrected = np.array([correction.apply(*p) for p in predicted])
    residual = float(np.sqrt(np.mean(np.sum((corrected - targets) ** 2, axis=1))))
    if residual > MAX_RESIDUAL:
        raise ValueError("The gaze did not follow the dots closely enough.")
    return correction, residual


class RecenterSession:
    """Shows RECENTER_POINTS one at a time and gathers the raw gaze on each."""

    def __init__(self, now: float):
        self._index = 0
        self._dot_started = now + LEAD_IN_S
        self._last_update = now
        self._samples: list[list[tuple[float, float]]] = [[] for _ in RECENTER_POINTS]
        self.error: str | None = None

    @property
    def finished(self) -> bool:
        return self._index >= len(RECENTER_POINTS) or self.error is not None

    @property
    def index(self) -> int:
        return self._index

    @property
    def target(self) -> tuple[float, float] | None:
        return None if self.finished else RECENTER_POINTS[self._index]

    def progress(self, now: float) -> float:
        """0..1 through the current dot's collection, for the on-screen ring."""
        return min(1.0, max(0.0, (now - self._dot_started - SETTLE_S) / COLLECT_S))

    def update(self, now: float, prediction: tuple[float, float] | None):
        """Feed one new raw (uncorrected) gaze prediction, or None for no frame."""
        if self.finished:
            return
        gap = now - self._last_update
        self._last_update = now
        if gap > STALL_S:
            self._dot_started += gap
        elapsed = now - self._dot_started
        if elapsed < 0:
            return
        if (prediction is not None and elapsed >= SETTLE_S
                and all(math.isfinite(v) for v in prediction)):
            self._samples[self._index].append(prediction)
        if elapsed < SETTLE_S + COLLECT_S:
            return
        if len(self._samples[self._index]) >= MIN_SAMPLES:
            self._index += 1
            self._dot_started = now
        elif elapsed >= MAX_DOT_S:
            self.error = (f"Eyes were not clear on dot {self._index + 1} of {len(RECENTER_POINTS)} "
                          f"({len(self._samples[self._index])} clear frames). "
                          "Keep them open and try again.")

    def result(self) -> tuple[ScreenCorrection, float]:
        """The fitted correction; raises ValueError if the session failed."""
        if self.error is not None:
            raise ValueError(self.error)
        if self._index < len(RECENTER_POINTS):
            raise ValueError("Re-centre is not finished.")
        pairs = [(tuple(np.median(np.array(s), axis=0)), target)
                 for s, target in zip(self._samples, RECENTER_POINTS)]
        return fit_correction(pairs)


def save_recenter(path: Path, profile_id: str, correction: ScreenCorrection, residual: float,
                  posture: PostureReference | None = None):
    record = RecenterFile(profile_id=profile_id, created_at=datetime.now().astimezone(),
                          matrix=correction.as_list(), residual_fraction=residual,
                          posture=posture)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)


def load_recenter_record(path: Path, profile_id: str) -> RecenterFile | None:
    """The saved re-centre for ``profile_id``; None after a new calibration."""
    try:
        record = RecenterFile.model_validate_json(path.read_text("utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValidationError) as exc:
        logger.warning("Ignoring unreadable re-centre file: %s", exc)
        return None
    return record if record.profile_id == profile_id else None


def load_recenter(path: Path, profile_id: str) -> ScreenCorrection | None:
    record = load_recenter_record(path, profile_id)
    return ScreenCorrection(record.matrix) if record is not None else None
