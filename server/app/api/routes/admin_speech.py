"""Admin: an assistive user's speech language (extension)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.accounts.guards import PEOPLE_SET, legacy_only
from app.api.deps import DatabaseSafeRoute, get_db, require_admin
from app.api.routes.speech import LanguageRead, LanguageWrite
from app.models.user import User
from app.services import admin_service, speech_language_service
from app.services.admin_service import AdminError
from app.services.speech_language_service import LanguageError

router = APIRouter(prefix="/admin/users", tags=["admin"], route_class=DatabaseSafeRoute)


def _target(db: Session, user_id: int) -> User:
    try:
        return admin_service.assistive_user(db, user_id)
    except AdminError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{user_id}/language", response_model=LanguageRead)
def language(user_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return LanguageRead(language=speech_language_service.get_language(db, _target(db, user_id)))


@router.put("/{user_id}/language", response_model=LanguageRead, dependencies=[Depends(legacy_only(PEOPLE_SET))])
def set_language(user_id: int, body: LanguageWrite, db: Session = Depends(get_db),
                 admin: User = Depends(require_admin)):
    try:
        return LanguageRead(language=speech_language_service.set_language(
            db, _target(db, user_id), body.language, actor=admin))
    except LanguageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
