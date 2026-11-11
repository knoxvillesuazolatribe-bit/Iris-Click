"""Learn from every click: keeps correcting gaze drift while IrisClick is used.

A left-wink click on a control the cursor snapped to tells us where the person
was really looking (the control's centre), so each such click gives one pair
(where the mapping thought they looked, where they looked). With enough recent
pairs the same affine correction the 5-dot re-centre uses is refitted
(core/calibration/recenter.fit_correction, same limits) and the live correction
moves only part of the way towards it, so the cursor never jumps.
WebGazer keeps calibrating from clicks the same way (Papoutsaki et al., 2016).

Safeguards: only snapped, small controls count; clicks must be spread over the
screen (a big tile's centre is not
where the eyes were); implausible fits are refused by fit_correction; the
learning resets on a re-centre or recalibration; off unless CLICK_LEARNING=on.

Everything is in screen fractions, like ScreenCorrection.
"""

import logging
import os
from collections import deque

import numpy as np

from app.core.calibration.recenter import fit_correction
from app.core.gaze.screen_mapper import ScreenCorrection

logger = logging.getLogger("irisclick.worker.click_learning")

ENV_NAME = "CLICK_LEARNING"
MAX_PAIRS = 12
MIN_PAIRS = 5
BLEND = 0.3
# Controls wider or taller than this do not pin down where the eyes were.
MAX_TARGET_PX = 160
# A click this far (screen fraction) from the control's centre is not trusted.
MAX_OFFSET = 0.15
# Clicks bunched in one spot cannot measure scale; they must cover this much of the
# screen (fraction, along x or y) before a correction is fitted.
MIN_SPREAD = 0.15


def enabled_from_env() -> bool:
    if os.environ.get(ENV_NAME) is not None:
        return os.environ[ENV_NAME].strip().lower() in ("on", "1", "true", "yes")
    try:
        from dotenv import dotenv_values

        from app.config import SERVER_DIR
        value = dotenv_values(SERVER_DIR / ".env").get(ENV_NAME) or ""
    except Exception:  # noqa: BLE001
        return False
    return value.strip().lower() in ("on", "1", "true", "yes")


def _matrix(correction: ScreenCorrection | None) -> np.ndarray:
    if correction is None:
        return np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    return np.asarray(correction.matrix, dtype=float).reshape(2, 3)


def remove_correction(correction: ScreenCorrection | None, x: float, y: float) -> tuple[float, float]:
    """The mapping's own estimate behind a corrected point (inverse of the affine)."""
    m = _matrix(correction)
    full = np.vstack([m, [0.0, 0.0, 1.0]])
    try:
        ux, uy, _ = np.linalg.solve(full, [x, y, 1.0])
    except np.linalg.LinAlgError:
        return x, y
    return float(ux), float(uy)


class ClickLearner:
    def __init__(self, enabled: bool = False, max_pairs: int = MAX_PAIRS, min_pairs: int = MIN_PAIRS,
                 blend: float = BLEND, max_target_px: int = MAX_TARGET_PX, max_offset: float = MAX_OFFSET):
        self.enabled = enabled
        self.min_pairs = min_pairs
        self.blend = blend
        self.max_target_px = max_target_px
        self.max_offset = max_offset
        self.pairs: deque = deque(maxlen=max_pairs)
        self.updates = 0

    def reset(self) -> None:
        self.pairs.clear()

    def observe_click(self, gaze_px: tuple[float, float] | None, target, screen: tuple[int, int],
                      correction: ScreenCorrection | None) -> ScreenCorrection | None:
        """One snapped click. ``gaze_px``: the corrected gaze estimate (before snapping) just
        before the eyes closed; ``target``: the snapped control (TargetRect) or None.
        Returns the new live correction, or None to keep the current one."""
        if not self.enabled or gaze_px is None or target is None:
            return None
        if target.width > self.max_target_px or target.height > self.max_target_px:
            return None
        w, h = screen
        gx, gy = gaze_px[0] / w, gaze_px[1] / h
        tx = (target.left + target.right) / 2 / w
        ty = (target.top + target.bottom) / 2 / h
        if np.hypot(gx - tx, gy - ty) > self.max_offset:
            return None
        self.pairs.append((remove_correction(correction, gx, gy), (tx, ty)))
        if len(self.pairs) < self.min_pairs:
            return None
        targets = np.array([t for _, t in self.pairs])
        if np.ptp(targets[:, 0]) < MIN_SPREAD and np.ptp(targets[:, 1]) < MIN_SPREAD:
            return None
        try:
            fitted, residual = fit_correction(list(self.pairs))
        except ValueError as exc:
            logger.info("Click learning: fit refused (%s)", exc)
            return None
        blended = (1.0 - self.blend) * _matrix(correction) + self.blend * fitted.matrix
        self.updates += 1
        logger.info("Click learning: correction updated from %d clicks (residual %.3f)",
                    len(self.pairs), residual)
        return ScreenCorrection(blended)
