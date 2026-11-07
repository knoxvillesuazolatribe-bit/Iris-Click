"""Home Suite and Gaze Tracking page for the signed-in assistive user.

Start/Stop go through the existing tracking service unchanged; this module
only picks the user's own calibration, reads the worker's live status and
writes system_logs.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.calibration_record import STATUS_SUCCESSFUL, CalibrationRecord
from app.models.timestamps import as_utc
from app.models.user import User
from app.services.assistive_service import NO_CALIBRATION, NOT_ON_THIS_COMPUTER, profile_on_disk
from app.services.system_log_service import log_activity
from app.workers.worker_state import read_state, state_path

ACTIVE, PAUSED, INACTIVE = "active", "paused", "inactive"


class HomeError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def gesture_guide(settings: Settings) -> list[dict[str, str]]:
    """Only gestures the tracking worker performs today, as configured."""
    right_action = "Go back" if settings.right_blink_action == "go_back" else "Undo"
    left_eye, right_eye = ("Click", right_action)
    if settings.swap_blink_sides:
        left_eye, right_eye = right_eye, left_eye
    guide = [{"gesture": "Look around the screen", "action": "Moves the cursor"}]
    for gesture, action in (("Wink your left eye", left_eye), ("Wink your right eye", right_eye)):
        if action != "Click" or settings.blink_click_enabled:
            guide.append({"gesture": gesture, "action": action})
    guide.append({"gesture": "Close both eyes for a moment", "action": "Takes a screenshot"})
    guide.append({"gesture": "Close both eyes twice", "action": "Opens or closes the keyboard"})
    if settings.edge_scroll_enabled:
        guide.append({"gesture": "Look at the top or bottom edge",
                      "action": "Scrolls up or down"})
    if settings.dwell_click_enabled:
        seconds = f"{settings.dwell_ms / 1000:g}"
        unit = "second" if seconds == "1" else "seconds"
        guide.append({"gesture": "Keep looking at one spot",
                      "action": f"Clicks after {seconds} {unit}"})
    return guide


@dataclass(frozen=True)
class Calibration:
    profile_id: str
    profile_name: str
    calibrated_at: datetime | None
    accuracy_score: Decimal | None


def _calibrations(db: Session, user: User) -> list[CalibrationRecord]:
    return db.scalars(
        select(CalibrationRecord)
        .where(CalibrationRecord.user_id == user.user_id,
               CalibrationRecord.status == STATUS_SUCCESSFUL,
               CalibrationRecord.profile_file_id.is_not(None))
        .order_by(CalibrationRecord.calibration_date.desc(),
                  CalibrationRecord.calibration_id.desc())
    ).all()


def _as_calibration(record: CalibrationRecord) -> Calibration:
    return Calibration(profile_id=record.profile_file_id, profile_name=record.profile_name,
                       calibrated_at=as_utc(record.calibration_date),
                       accuracy_score=record.accuracy_score)


def usable_calibration(db: Session, user: User,
                       profiles_dir: Path) -> tuple[Calibration | None, str | None]:
    """The user's latest successful calibration on this computer, or why there is none."""
    records = _calibrations(db, user)
    usable = next((r for r in records if profile_on_disk(profiles_dir, r.profile_file_id)), None)
    if usable is not None:
        return _as_calibration(usable), None
    return None, NOT_ON_THIS_COMPUTER if records else NO_CALIBRATION


def tracking_view(db: Session, user: User, settings: Settings, tracking) -> dict:
    status = tracking.status()
    calibration, reason = usable_calibration(db, user, settings.profiles_dir)
    view = {"state": INACTIVE, "status_text": None, "running_profile_is_mine": None,
            "started_at": None, "calibration": calibration,
            "calibration_unavailable_reason": reason, "live": None}
    if not status.running:
        return view

    mine = {r.profile_file_id: r for r in _calibrations(db, user)}
    running_mine = status.profile_id in mine
    if running_mine:
        view["calibration"] = _as_calibration(mine[status.profile_id])
    live = read_state(state_path(settings), status.pid) if status.pid else None
    view.update(
        state=PAUSED if live and live["paused"] else ACTIVE,
        status_text=live["status"] if live else None,
        running_profile_is_mine=running_mine,
        started_at=status.started_at,
        live=live,
    )
    return view


def start_tracking(db: Session, user: User, settings: Settings, tracking) -> dict:
    calibration, reason = usable_calibration(db, user, settings.profiles_dir)
    if calibration is None:
        raise HomeError(409, reason)
    before = tracking.status()
    try:
        tracking.start(calibration.profile_id)
    except (LookupError, ValueError) as exc:
        raise HomeError(409, f"{exc} You can choose Calibrate instead.") from exc
    if not (before.running and before.profile_id == calibration.profile_id):
        log_activity("tracking_started",
                     f"{user.full_name} started eye tracking with "
                     f"calibration '{calibration.profile_name}'", user.user_id, session=db)
        db.commit()
    return tracking_view(db, user, settings, tracking)


def restart_tracking(db: Session, user: User, settings: Settings, tracking) -> dict:
    """Stops tracking and starts it again with the user's own calibration, so new
    settings take effect. A failed start is reported, never hidden."""
    calibration, reason = usable_calibration(db, user, settings.profiles_dir)
    if calibration is None:
        raise HomeError(409, reason)
    tracking.stop()
    try:
        tracking.start(calibration.profile_id)
    except (LookupError, ValueError) as exc:
        log_activity("tracking_stopped", f"{user.full_name} restarted eye tracking but it "
                     "could not start again", user.user_id, session=db)
        db.commit()
        raise HomeError(409, f"Eye tracking stopped but could not start again: {exc} "
                             "Choose Start to try again.") from exc
    log_activity("tracking_restarted",
                 f"{user.full_name} restarted eye tracking to apply new settings",
                 user.user_id, session=db)
    db.commit()
    return tracking_view(db, user, settings, tracking)


def stop_tracking(db: Session, user: User, settings: Settings, tracking) -> dict:
    was_running = tracking.status().running
    tracking.stop()
    if was_running:
        log_activity("tracking_stopped", f"{user.full_name} stopped eye tracking",
                     user.user_id, session=db)
        db.commit()
    return tracking_view(db, user, settings, tracking)
