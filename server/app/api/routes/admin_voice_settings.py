"""Admin: an assistive user's voice settings (clearer TTS), same rules as the user's own."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_admin
from app.api.routes.neural_tts import VoiceSettingsRead, VoiceSettingsWrite, fail, settings_read
from app.models.user import User
from app.services import admin_service
from app.services import neural_tts_service as tts
from app.services.admin_service import AdminError
from app.services.neural_tts_service import NeuralTtsError

router = APIRouter(prefix="/admin/users", tags=["admin"], route_class=DatabaseSafeRoute)


def _target(db: Session, user_id: int) -> User:
    try:
        return admin_service.assistive_user(db, user_id)
    except AdminError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{user_id}/voice-settings", response_model=VoiceSettingsRead)
def user_settings(user_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return settings_read(db, _target(db, user_id))


@router.put("/{user_id}/voice-settings", response_model=VoiceSettingsRead)
def save_user_settings(user_id: int, body: VoiceSettingsWrite, db: Session = Depends(get_db),
                       admin: User = Depends(require_admin)):
    user = _target(db, user_id)
    try:
        tts.save_settings(db, user, body.model_dump(), actor=admin)
    except NeuralTtsError as exc:
        fail(exc)
    return settings_read(db, user)


@router.post("/{user_id}/voice-settings/reset", response_model=VoiceSettingsRead)
def reset_user_settings(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = _target(db, user_id)
    tts.reset_settings(db, user, actor=admin)
    return settings_read(db, user)
