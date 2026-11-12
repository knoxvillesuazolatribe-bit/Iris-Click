"""IrisClick Desktop: the calibration a new person does before their account exists.

POST /api/desktop/pending-calibration/allow    let the next calibration start with nobody linked
GET  /api/desktop/pending-calibration          the newest ownerless calibration of the last 15 min
POST /api/desktop/pending-calibration/attach   give it to the person now linked, upload it
POST /api/desktop/pending-calibration/discard  delete it (Back / Cancel)
POST /api/desktop/pending-calibration/hold-tracking  keep eye tracking off until the account exists

Only allowed websites reach these routes (origin_guard). See app/accounts/pending_calibration.py.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.accounts import pending_calibration as pending
from app.api.deps import DatabaseSafeRoute, get_db
from app.config import get_settings
from app.services import active_user

router = APIRouter(prefix="/desktop/pending-calibration", tags=["desktop"], route_class=DatabaseSafeRoute)


class PendingRead(BaseModel):
    pending: bool
    profile_file_id: str | None = None
    accuracy_score: float | None = None
    low_accuracy: bool = False


class PendingRequest(BaseModel):
    profile_file_id: str | None = Field(default=None, max_length=64)


class AttachRead(BaseModel):
    attached: bool
    uploaded: bool


@router.post("/allow")
def allow() -> dict:
    # A new person is about to calibrate: unlink whoever used this computer before, or Desktop
    # would save the calibration as theirs instead of keeping it for the new account.
    active_user.set_user_id(None)
    pending.allow_new_account()
    return {"allowed": True}


@router.post("/hold-tracking")
def hold_tracking() -> dict:
    return {"held": pending.hold_tracking()}


@router.get("", response_model=PendingRead)
def current(db: Session = Depends(get_db)) -> PendingRead:
    found = pending.find_pending(db, get_settings().profiles_dir)
    if found is None:
        return PendingRead(pending=False)
    return PendingRead(pending=True, profile_file_id=found.profile_file_id, accuracy_score=found.accuracy_score,
                       low_accuracy=found.low_accuracy)


@router.post("/attach", response_model=AttachRead)
def attach(body: PendingRequest, db: Session = Depends(get_db)) -> AttachRead:
    try:
        _row, uploaded = pending.attach(db, get_settings().profiles_dir, body.profile_file_id)
    except pending.PendingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return AttachRead(attached=True, uploaded=uploaded)


@router.post("/discard")
def discard(body: PendingRequest, db: Session = Depends(get_db)) -> dict:
    return {"discarded": pending.discard(db, get_settings().profiles_dir, body.profile_file_id)}
