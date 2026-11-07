"""Online (browser) calibrations for the online copy.

The browser fits its own gaze model (site/src/online-gaze). Results go into
the same calibration_profiles table as the PC's, so admin reports and logs
count them, with feature_source ONLINE_SOURCE and no profile file. The PC
only uses calibrations whose profile file is on its own disk, so these never
replace a PC calibration.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_assistive
from app.models.calibration_record import STATUS_FAILED, STATUS_SUCCESSFUL, CalibrationRecord
from app.models.timestamps import as_utc
from app.models.user import User
from app.services.calibration_records import (FAILURE_REASONS, LOG_FAILED, LOG_SUCCESS,
                                              accuracy_percent)
from app.services.system_log_service import log_activity

ONLINE_SOURCE = "web_eye_midpoint_v1"
PROFILE_NAME = "Online (browser)"
# Accepted with a low-accuracy note above the first limit, refused above the
# second (the PC's MAX_FIT_ERROR_FRACTION / MAX_LOW_ACCURACY_FRACTION).
LOW_ACCURACY_FRACTION = 0.06
MAX_ACCURACY_FRACTION = 0.10

Finite = Annotated[float, Field(allow_inf_nan=False)]


class GazeModelData(BaseModel):
    source: Literal["web_eye_midpoint_v1"]
    version: int = Field(ge=1, le=100)
    mean: list[Finite] = Field(min_length=5, max_length=5)
    scale: list[Finite] = Field(min_length=5, max_length=5)
    coefX: list[Finite] = Field(min_length=6, max_length=6)
    coefY: list[Finite] = Field(min_length=6, max_length=6)
    stretch: list[Finite] = Field(min_length=4, max_length=4)


class Viewport(BaseModel):
    w: int = Field(gt=0, le=20000)
    h: int = Field(gt=0, le=20000)


class OnlineCalibrationIn(BaseModel):
    status: Literal["Successful", "Failed"]
    error_fraction: Finite | None = Field(None, ge=0, le=10)
    sample_count: int = Field(0, ge=0, le=100000)
    reason: Literal["dot_not_clear", "fit_failed", "not_accurate_enough"] | None = None
    model: GazeModelData | None = None
    viewport: Viewport | None = None


class OnlineCalibrationOut(BaseModel):
    calibration_id: int
    calibrated_at: str
    accuracy_score: float | None
    low_accuracy: bool
    model: GazeModelData
    viewport: Viewport | None = None


router = APIRouter(prefix="/me/online-calibration", tags=["online copy"],
                   route_class=DatabaseSafeRoute)


def _out(record: CalibrationRecord) -> OnlineCalibrationOut:
    data = record.calibration_data or {}
    return OnlineCalibrationOut(
        calibration_id=record.calibration_id,
        calibrated_at=as_utc(record.calibration_date).isoformat(),
        accuracy_score=float(record.accuracy_score) if record.accuracy_score is not None else None,
        low_accuracy=bool(record.low_accuracy),
        model=GazeModelData.model_validate(data.get("model")),
        viewport=data.get("viewport"),
    )


@router.get("", response_model=OnlineCalibrationOut | None)
def latest(user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    """The user's latest successful online calibration, or null."""
    records = db.scalars(
        select(CalibrationRecord)
        .where(CalibrationRecord.user_id == user.user_id,
               CalibrationRecord.status == STATUS_SUCCESSFUL,
               CalibrationRecord.feature_source == ONLINE_SOURCE)
        .order_by(CalibrationRecord.calibration_date.desc(), CalibrationRecord.calibration_id.desc())
        .limit(5)
    ).all()
    for record in records:
        try:
            return _out(record)
        except ValueError:  # a damaged row: try the one before it
            continue
    return None


@router.post("", response_model=OnlineCalibrationOut | None, status_code=201)
def save(body: OnlineCalibrationIn, user: User = Depends(require_assistive),
         db: Session = Depends(get_db)):
    """Records a finished online calibration (successful or failed)."""
    error = body.error_fraction
    accuracy = accuracy_percent(error)
    success = (body.status == STATUS_SUCCESSFUL and body.model is not None and error is not None
               and error <= MAX_ACCURACY_FRACTION)
    if success:
        record = CalibrationRecord(
            user_id=user.user_id, profile_name=PROFILE_NAME, status=STATUS_SUCCESSFUL,
            accuracy_score=accuracy, error_fraction=error,
            low_accuracy=error > LOW_ACCURACY_FRACTION, feature_source=ONLINE_SOURCE,
            sample_count=body.sample_count,
            calibration_data={"model": body.model.model_dump(),
                              "viewport": body.viewport.model_dump() if body.viewport else None},
        )
        description = f"Online calibration saved: accuracy {accuracy}% (browser)"
        log_type = LOG_SUCCESS
    else:
        reason = body.reason or ("not_accurate_enough" if body.status == STATUS_SUCCESSFUL else "fit_failed")
        text = FAILURE_REASONS[reason]
        record = CalibrationRecord(
            user_id=user.user_id, profile_name=PROFILE_NAME, status=STATUS_FAILED,
            accuracy_score=accuracy, error_fraction=error, feature_source=ONLINE_SOURCE,
            sample_count=body.sample_count, failure_reason=text,
        )
        description = f"Online calibration failed: {text}" + (f" Accuracy {accuracy}%." if accuracy is not None else "")
        log_type = LOG_FAILED
    db.add(record)
    db.flush()
    log_activity(log_type, description, user.user_id, session=db)
    db.commit()
    return _out(record) if success else None
