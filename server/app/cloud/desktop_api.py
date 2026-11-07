"""Hosted API for IrisClick Desktop (database option 2: the Supabase password stays here).

IrisClick Desktop keeps a small local database on the PC and syncs it through these
routes with the 12-hour desktop token from app/cloud/desktop.py:

    GET  /api/desktop/profile        the linked user, their accessibility settings and
                                     the admin's global defaults (what the worker needs)
    POST /api/desktop/calibrations   new calibration results  -> calibration_profiles
    POST /api/desktop/logs           calibration / screenshot activity -> system_logs

Every row is saved for the token's own user only, whatever the request says, and only
these kinds of rows are accepted. Re-sent rows (after a lost answer) are not duplicated.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db
from app.models.accessibility_settings import AccessibilitySettings
from app.models.calibration_record import STATUS_FAILED, STATUS_SUCCESSFUL, CalibrationRecord
from app.models.system_log import SystemLog
from app.models.system_settings import SystemSettings
from app.models.timestamps import as_utc
from app.models.user import ROLE_ASSISTIVE_USER, STATUS_ACTIVE, User
from app.services import desktop_tokens
from app.services.desktop_tokens import DESKTOP, TokenError

SIGN_IN_AGAIN = "IrisClick Desktop needs to be linked again: choose your name on the IrisClick website."
SYNCED_LOG_TYPES = ("calibration", "calibration_failed", "screenshot")
MAX_ROWS = 50

router = APIRouter(prefix="/desktop", tags=["desktop api"], route_class=DatabaseSafeRoute)

ACCESSIBILITY_COLUMNS = ("dwell_enabled", "dwell_ms", "cursor_smoothing", "blink_to_click",
                         "blink_sensitivity", "voice_volume", "edge_scroll_enabled")
GLOBAL_COLUMNS = ("app_name", *ACCESSIBILITY_COLUMNS)


def desktop_user(authorization: Annotated[str | None, Header()] = None,
                 db: Session = Depends(get_db)) -> User:
    token = (authorization or "").removeprefix("Bearer ").strip()
    try:
        user_id = desktop_tokens.read(token, DESKTOP)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=SIGN_IN_AGAIN) from exc
    user = db.get(User, user_id)
    if user is None or user.role != ROLE_ASSISTIVE_USER or user.status != STATUS_ACTIVE:
        raise HTTPException(status_code=401, detail=SIGN_IN_AGAIN)
    return user


def _columns(row, names) -> dict | None:
    return None if row is None else {name: getattr(row, name) for name in names}


@router.get("/profile")
def profile(user: User = Depends(desktop_user), db: Session = Depends(get_db)) -> dict:
    own = db.scalar(select(AccessibilitySettings).where(AccessibilitySettings.user_id == user.user_id))
    defaults = db.get(SystemSettings, 1) or db.scalar(select(SystemSettings).limit(1))
    return {
        "user": {"user_id": user.user_id, "full_name": user.full_name, "role": user.role,
                 "status": user.status},
        "accessibility": _columns(own, ACCESSIBILITY_COLUMNS),
        "global_defaults": _columns(defaults, GLOBAL_COLUMNS),
    }


Finite = Annotated[float, Field(allow_inf_nan=False)]


class CalibrationIn(BaseModel):
    profile_file_id: str | None = Field(None, max_length=64)
    profile_name: str = Field("", max_length=60)
    status: Literal["Successful", "Failed"]
    accuracy_score: Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)] | None = None
    error_fraction: Finite | None = None
    low_accuracy: bool | None = None
    feature_source: str | None = Field(None, max_length=50)
    camera_index: int | None = Field(None, ge=0, le=99)
    sample_count: int | None = Field(None, ge=0, le=1_000_000)
    calibration_data: dict[str, Any] | None = None
    failure_reason: str | None = Field(None, max_length=500)
    calibration_date: datetime


class CalibrationBatch(BaseModel):
    records: list[CalibrationIn] = Field(max_length=MAX_ROWS)


class LogIn(BaseModel):
    activity_type: Literal["calibration", "calibration_failed", "screenshot"]
    activity_description: str | None = Field(None, max_length=1000)
    log_date: datetime


class LogBatch(BaseModel):
    logs: list[LogIn] = Field(max_length=MAX_ROWS)


@router.post("/calibrations")
def save_calibrations(body: CalibrationBatch, user: User = Depends(desktop_user),
                      db: Session = Depends(get_db)) -> dict:
    saved = 0
    for rec in body.records:
        when = as_utc(rec.calibration_date)
        if rec.profile_file_id:
            exists = db.scalar(select(CalibrationRecord.calibration_id)
                               .where(CalibrationRecord.profile_file_id == rec.profile_file_id))
        else:
            exists = db.scalar(select(CalibrationRecord.calibration_id).where(
                CalibrationRecord.user_id == user.user_id, CalibrationRecord.calibration_date == when,
                CalibrationRecord.status == rec.status, CalibrationRecord.profile_name == rec.profile_name))
        if exists:
            continue
        status = STATUS_SUCCESSFUL if rec.status == "Successful" else STATUS_FAILED
        db.add(CalibrationRecord(user_id=user.user_id, **rec.model_dump(exclude={"status", "calibration_date"}),
                                 status=status, calibration_date=when))
        saved += 1
    db.commit()
    return {"received": len(body.records), "saved": saved}


@router.post("/logs")
def save_logs(body: LogBatch, user: User = Depends(desktop_user), db: Session = Depends(get_db)) -> dict:
    saved = 0
    for log in body.logs:
        when = as_utc(log.log_date)
        exists = db.scalar(select(SystemLog.log_id).where(
            SystemLog.user_id == user.user_id, SystemLog.activity_type == log.activity_type,
            SystemLog.log_date == when, SystemLog.activity_description == log.activity_description))
        if exists:
            continue
        db.add(SystemLog(user_id=user.user_id, activity_type=log.activity_type,
                         activity_description=log.activity_description, log_date=when))
        saved += 1
    db.commit()
    return {"received": len(body.logs), "saved": saved}
