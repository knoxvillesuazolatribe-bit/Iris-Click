"""App shortcuts for the signed-in assistive user (Phase 9)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_assistive
from app.models.user import User
from app.services import apps_service
from app.services.apps_service import AppError
from app.services.system_log_service import log_activity

router = APIRouter(prefix="/me/apps", tags=["apps"], route_class=DatabaseSafeRoute)


class AppRead(BaseModel):
    app_id: str
    label: str
    note: str | None


class LaunchRead(BaseModel):
    launched: bool
    label: str


@router.get("", response_model=list[AppRead])
def list_apps(_user: User = Depends(require_assistive)):
    return [AppRead(app_id=a.app_id, label=a.label, note=a.note) for a in apps_service.available()]


@router.post("/{app_id}/launch", response_model=LaunchRead)
def launch_app(app_id: str, user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    try:
        app = apps_service.launch(app_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    log_activity("app_launched", f"{user.full_name} opened {app.label}", user.user_id, session=db)
    db.commit()
    return LaunchRead(launched=True, label=app.label)
