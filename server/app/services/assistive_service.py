"""Assistive-user sign-in by name tile, and what "Continue" can resume.

A tile offers "Continue with saved calibration" only when the user's latest
successful calibration that still has its JSON profile on this computer
exists; otherwise it says why, so the user picks "Calibrate" instead.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.calibration_record import STATUS_SUCCESSFUL, CalibrationRecord
from app.models.timestamps import as_utc
from app.models.user import ROLE_ASSISTIVE_USER, STATUS_ACTIVE, User
from app.services import active_user
from app.services.system_log_service import log_activity

NO_CALIBRATION = "No saved calibration yet. Choose Calibrate."
NOT_ON_THIS_COMPUTER = "Your saved calibration is not on this computer. Choose Calibrate."


class SelectionError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class Tile:
    user_id: int
    full_name: str
    last_calibrated_at: datetime | None
    accuracy_score: Decimal | None
    continue_profile_id: str | None
    continue_unavailable_reason: str | None


def profile_on_disk(profiles_dir: Path, profile_file_id: str | None) -> bool:
    return bool(profile_file_id) and (profiles_dir / f"{profile_file_id}.json").is_file()


def tile_for(db: Session, user: User, profiles_dir: Path) -> Tile:
    calibrations = db.scalars(
        select(CalibrationRecord)
        .where(CalibrationRecord.user_id == user.user_id,
               CalibrationRecord.status == STATUS_SUCCESSFUL)
        .order_by(CalibrationRecord.calibration_date.desc(), CalibrationRecord.calibration_id.desc())
    ).all()
    latest = calibrations[0] if calibrations else None
    usable = next((c for c in calibrations if profile_on_disk(profiles_dir, c.profile_file_id)),
                  None)
    reason = None
    if usable is None:
        reason = NOT_ON_THIS_COMPUTER if latest else NO_CALIBRATION
    return Tile(
        user_id=user.user_id,
        full_name=user.full_name,
        last_calibrated_at=as_utc(latest.calibration_date) if latest else None,
        accuracy_score=latest.accuracy_score if latest else None,
        continue_profile_id=usable.profile_file_id if usable else None,
        continue_unavailable_reason=reason,
    )


def list_tiles(db: Session, profiles_dir: Path) -> list[Tile]:
    """Every active assistive user, alphabetically (inactive users are hidden)."""
    users = db.scalars(
        select(User)
        .where(User.role == ROLE_ASSISTIVE_USER, User.status == STATUS_ACTIVE)
        .order_by(User.full_name, User.user_id)
    ).all()
    return [tile_for(db, user, profiles_dir) for user in users]


def select_user(db: Session, user_id: int) -> User:
    """The active assistive user behind a tile; makes them this computer's user."""
    user = db.get(User, user_id)
    if user is None or user.role != ROLE_ASSISTIVE_USER:
        raise SelectionError(404, "That user was not found. Go back and pick your name again.")
    if user.status != STATUS_ACTIVE:
        raise SelectionError(403, "This account is inactive. Ask your PDAO administrator.")
    active_user.set_user_id(user.user_id)
    log_activity("user_selected", f"{user.full_name} signed in by name tile", user.user_id,
                 session=db)
    return user
