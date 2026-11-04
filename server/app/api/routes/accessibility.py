"""Accessibility Settings for the signed-in assistive user (admins edit them in Phase 8)."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_assistive
from app.config import get_settings
from app.models.user import User
from app.schemas.accessibility import AccessibilitySettingsRead, AccessibilitySettingsWrite
from app.services import accessibility_service
from app.services.accessibility_service import FriendlySettings, SettingsError

router = APIRouter(prefix="/me/settings", tags=["settings"], route_class=DatabaseSafeRoute)


def _read(db: Session, user: User) -> AccessibilitySettingsRead:
    base = get_settings()
    values, is_default = accessibility_service.current(db, user, base)
    return AccessibilitySettingsRead(
        **asdict(values), is_default=is_default,
        defaults=AccessibilitySettingsWrite(**asdict(accessibility_service.defaults(base))))


@router.get("", response_model=AccessibilitySettingsRead)
def read_settings(user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    return _read(db, user)


@router.put("", response_model=AccessibilitySettingsRead)
def save_settings(body: AccessibilitySettingsWrite, user: User = Depends(require_assistive),
                  db: Session = Depends(get_db)):
    try:
        accessibility_service.save(db, user, FriendlySettings(**body.model_dump()))
    except SettingsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return _read(db, user)


@router.post("/reset", response_model=AccessibilitySettingsRead)
def reset_settings(user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    accessibility_service.reset(db, user)
    return _read(db, user)
