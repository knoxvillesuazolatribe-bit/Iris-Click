"""The calibration a new person does before their account exists (file 07, plan D4, build step 8).

Figure 16 has a new person calibrate first and choose a username after. IrisClick Desktop
normally refuses to calibrate until someone is linked, so the website first asks for a
short window (``allow_new_account``); the calibration then runs as usual and is saved on
this computer with no owner. When the account is created and linked, ``attach`` gives the
newest such calibration to that person and uploads it to the hosted server; Back or
Cancel calls ``discard``. Only calibrations from the last 15 minutes count, so an old
ownerless calibration is never handed to the wrong person.
"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.calibration_record import STATUS_SUCCESSFUL, CalibrationRecord
from app.models.timestamps import as_utc, utc_now
from app.services import active_user
from app.services.system_log_service import log_activity

logger = logging.getLogger("irisclick.pending_calibration")

PENDING_FOR = timedelta(minutes=15)
ALLOW_FOR_S = 15 * 60

_lock = threading.Lock()
_allowed_until = 0.0


def allow_new_account(now: float | None = None) -> None:
    """Let the next calibration start with nobody linked (for 15 minutes)."""
    global _allowed_until
    with _lock:
        _allowed_until = (now if now is not None else time.monotonic()) + ALLOW_FOR_S


def close_window() -> None:
    global _allowed_until
    with _lock:
        _allowed_until = 0.0


def new_account_allowed(now: float | None = None) -> bool:
    with _lock:
        return (now if now is not None else time.monotonic()) < _allowed_until


@dataclass(frozen=True)
class Pending:
    calibration_id: int
    profile_file_id: str
    accuracy_score: float | None
    low_accuracy: bool


def _profile_path(profiles_dir: Path, profile_file_id: str) -> Path:
    return profiles_dir / f"{profile_file_id}.json"


def find_pending(db: Session, profiles_dir: Path, now=None) -> Pending | None:
    """The newest successful, ownerless calibration of the last 15 minutes that is still on disk."""
    since = (now or utc_now()) - PENDING_FOR
    rows = db.scalars(select(CalibrationRecord).where(
        CalibrationRecord.user_id.is_(None), CalibrationRecord.status == STATUS_SUCCESSFUL,
        CalibrationRecord.profile_file_id.is_not(None), CalibrationRecord.calibration_date >= since)
        .order_by(CalibrationRecord.calibration_date.desc(), CalibrationRecord.calibration_id.desc())).all()
    for row in rows:
        if as_utc(row.calibration_date) >= since and _profile_path(profiles_dir, row.profile_file_id).is_file():
            return Pending(row.calibration_id, row.profile_file_id,
                           float(row.accuracy_score) if row.accuracy_score is not None else None,
                           bool(row.low_accuracy))
    return None


class PendingError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code, self.message = status_code, message


NONE_PENDING = "There is no new calibration on this computer. Please calibrate again."
NOT_LINKED = "Your account is not linked to IrisClick Desktop yet. Please try again."


def _row(db: Session, profiles_dir: Path, profile_file_id: str | None, now=None) -> CalibrationRecord:
    pending = find_pending(db, profiles_dir, now)
    if pending is None or (profile_file_id is not None and pending.profile_file_id != profile_file_id):
        raise PendingError(404, NONE_PENDING)
    return db.get(CalibrationRecord, pending.calibration_id)


def attach(db: Session, profiles_dir: Path, profile_file_id: str | None = None, now=None,
           upload=None) -> tuple[CalibrationRecord, bool]:
    """Give the pending calibration to the person linked on this computer; returns (row, uploaded)."""
    user_id = active_user.get_user_id()
    if user_id is None:
        raise PendingError(409, NOT_LINKED)
    row = _row(db, profiles_dir, profile_file_id, now)
    row.user_id = user_id
    log_activity("calibration_attached", f"New-account calibration '{row.profile_name}' added to the account",
                 user_id, session=db)
    db.commit()
    close_window()
    uploaded = False
    try:
        uploaded = (upload or upload_to_hosted)(row)
    except Exception:  # noqa: BLE001 - the calibration stays on this PC; the account still works
        logger.warning("New-account calibration %s not uploaded", row.profile_file_id, exc_info=True)
    return row, uploaded


def discard(db: Session, profiles_dir: Path, profile_file_id: str | None = None, now=None) -> bool:
    """Delete the pending calibration (Back or Cancel). False when there was none."""
    close_window()
    try:
        row = _row(db, profiles_dir, profile_file_id, now)
    except PendingError:
        return False
    try:
        _profile_path(profiles_dir, row.profile_file_id).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete profile file %s", row.profile_file_id, exc_info=True)
    db.delete(row)
    db.commit()
    return True


def upload_to_hosted(row: CalibrationRecord) -> bool:
    """Send the attached calibration to the hosted server, as the regular sync does (desktop mode only)."""
    from app.api.routes import desktop_link
    from app.desktop_sync import sync
    if not sync.desktop_mode():
        return False  # PC-only install: the local database is the database
    session = desktop_link.load_session()
    if session is None:
        return False
    sync._call("POST", "/api/desktop/calibrations", session["desktop_token"],  # noqa: SLF001
               {"records": [sync._calibration_json(row)]})  # noqa: SLF001
    return True
