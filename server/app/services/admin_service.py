"""Admin module (Phase 8): dashboard counts and assistive-user management.

Users are never hard-deleted: deactivating hides their name tile, ends their
sign-in at once and keeps their history. Eye tracking is left running so
nobody suddenly loses control of the computer. Every change is logged as the admin.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.calibration_record import STATUS_SUCCESSFUL, CalibrationRecord
from app.models.sos import SosHistory
from app.models.system_log import SystemLog
from app.models.timestamps import as_utc, utc_now
from app.models.user import ROLE_ASSISTIVE_USER, STATUS_ACTIVE, STATUS_INACTIVE, User
from app.services import active_user, session_service
from app.services.system_log_service import log_activity

WEEK = timedelta(days=7)


class AdminError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# --- Dashboard -------------------------------------------------------------------------

def dashboard(db: Session) -> dict:
    since = utc_now() - WEEK
    return {
        "active_users": db.scalar(select(func.count()).select_from(User).where(
            User.role == ROLE_ASSISTIVE_USER, User.status == STATUS_ACTIVE)) or 0,
        "active_users_week": db.scalar(select(func.count(distinct(SystemLog.user_id))).where(
            SystemLog.activity_type == "user_selected", SystemLog.log_date >= since)) or 0,
        "sos_events": db.scalar(select(func.count(distinct(SosHistory.activation_id)))) or 0,
        "sos_events_week": db.scalar(select(func.count(distinct(SosHistory.activation_id)))
                                     .where(SosHistory.date_sent >= since)) or 0,
        "calibrations": db.scalar(select(func.count()).select_from(CalibrationRecord).where(
            CalibrationRecord.status == STATUS_SUCCESSFUL)) or 0,
        "calibrations_week": db.scalar(select(func.count()).select_from(CalibrationRecord).where(
            CalibrationRecord.status == STATUS_SUCCESSFUL,
            CalibrationRecord.calibration_date >= since)) or 0,
    }


# --- Users -------------------------------------------------------------------------------

@dataclass(frozen=True)
class CalibrationSummary:
    calibration_count: int
    latest_accuracy: Decimal | None
    last_calibrated_at: datetime | None


def calibration_summary(db: Session, user_id: int) -> CalibrationSummary:
    rows = db.scalars(select(CalibrationRecord)
                      .where(CalibrationRecord.user_id == user_id,
                             CalibrationRecord.status == STATUS_SUCCESSFUL)
                      .order_by(CalibrationRecord.calibration_date.desc(),
                                CalibrationRecord.calibration_id.desc())).all()
    latest = rows[0] if rows else None
    return CalibrationSummary(
        calibration_count=len(rows),
        latest_accuracy=latest.accuracy_score if latest else None,
        last_calibrated_at=as_utc(latest.calibration_date) if latest else None,
    )


def assistive_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.role != ROLE_ASSISTIVE_USER:
        raise AdminError(404, "That user was not found.")
    return user


def list_users(db: Session) -> list[tuple[User, CalibrationSummary]]:
    """Every account (admins too, as since Phase 2), with calibration summaries."""
    users = db.scalars(select(User).order_by(User.role, User.status, User.full_name,
                                             User.user_id)).all()
    return [(user, calibration_summary(db, user.user_id)) for user in users]


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def update_profile(db: Session, admin: User, user: User, full_name: str,
                   address: str | None, barangay: str | None) -> User:
    user.full_name = full_name.strip()
    user.address = _clean(address)
    user.barangay = _clean(barangay)
    log_activity("user_updated", f"{admin.full_name} updated the profile of {user.full_name}",
                 admin.user_id, session=db)
    db.commit()
    return user


def set_status(db: Session, admin: User, user: User, status: str) -> User:
    if status not in (STATUS_ACTIVE, STATUS_INACTIVE):
        raise AdminError(422, "Status must be active or inactive.")
    if user.status == status:
        return user
    user.status = status
    if status == STATUS_INACTIVE:
        ended = session_service.revoke_all_for_user(db, user.user_id)
        active_user.clear_if(user.user_id)
        log_activity("user_deactivated",
                     f"{admin.full_name} deactivated {user.full_name}"
                     + (f" and ended {ended} sign-in(s)" if ended else ""),
                     admin.user_id, session=db)
    else:
        log_activity("user_reactivated", f"{admin.full_name} reactivated {user.full_name}",
                     admin.user_id, session=db)
    db.commit()
    return user
