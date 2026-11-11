"""Quick re-centre once each time eye tracking starts.

A calibration is fitted for one sitting; a new sitting (leaning back, a new
chair position) roughly doubled the error on the benchmark recordings
(about 130 px -> 240-290 px), and the existing 5-dot re-centre brought it back
to about 140 px (scripts/simulate_calibration.py). So the tracking worker runs
that same re-centre once per start, hands-free, as soon as the person is in
front of the camera with eyes open for STEADY_S.

Skipped when the calibration is younger than FRESH_PROFILE_S (it was just fitted
for this sitting) and when AUTO_RECENTRE=off. A re-centre the person does not
follow fails safely and keeps the previous correction (tracking_worker).
"""

import os
from datetime import datetime

ENV_NAME = "AUTO_RECENTRE"
STEADY_S = 2.0
FRESH_PROFILE_S = 300.0
# Same floor as the calibration's "registered" eyes (calibration_service).
MIN_EAR = 0.15


def enabled_from_env() -> bool:
    value = os.environ.get(ENV_NAME)
    if value is None:
        try:
            from dotenv import dotenv_values

            from app.config import SERVER_DIR
            value = dotenv_values(SERVER_DIR / ".env").get(ENV_NAME)
        except Exception:  # noqa: BLE001 - anything odd keeps the default
            value = None
    return (value or "on").strip().lower() not in ("off", "0", "false", "no")


def profile_age_s(profile_id: str | None, now: datetime | None = None) -> float | None:
    """Seconds since the calibration was saved, from its id (``20261111T081351-…``)."""
    try:
        created = datetime.strptime((profile_id or "")[:15], "%Y%m%dT%H%M%S")
    except ValueError:
        return None
    return ((now or datetime.now()) - created).total_seconds()


class StartRecentre:
    def __init__(self, enabled: bool, profile_age: float | None):
        # A fresh calibration already fits this sitting.
        self.pending = enabled and not (profile_age is not None and 0 <= profile_age < FRESH_PROFILE_S)
        self._steady_since: float | None = None

    @classmethod
    def from_env(cls, profile_id: str | None) -> "StartRecentre":
        return cls(enabled_from_env(), profile_age_s(profile_id))

    def due(self, now: float, reading) -> bool:
        """True once: the first moment the face has been steady for STEADY_S."""
        if not self.pending:
            return False
        steady = (getattr(reading, "face_found", False) and getattr(reading, "eye_line", None)
                  and min(getattr(reading, "left_ear", 0.0), getattr(reading, "right_ear", 0.0)) >= MIN_EAR)
        if not steady:
            self._steady_since = None
            return False
        if self._steady_since is None:
            self._steady_since = now
        if now - self._steady_since < STEADY_S:
            return False
        self.pending = False
        return True
