"""Hosted server side of the web ↔ desktop link.

1. The signed-in user's page asks POST /api/me/desktop-link for a 5-minute link token.
2. The page gives it to IrisClick Desktop (POST http://127.0.0.1:8000/api/desktop/link).
3. The desktop app exchanges it here, POST /api/desktop/session, for a 12-hour desktop
   token and the user's name. This path is open past the site access code: it is
   protected by the signed token instead (the desktop app has no access-code cookie).
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_assistive
from app.models.user import ROLE_ASSISTIVE_USER, STATUS_ACTIVE, User
from app.services import desktop_tokens
from app.services.desktop_tokens import DESKTOP, LINK, TokenError
from app.services.system_log_service import log_activity

SESSION_PATH = "/desktop/session"
LINK_EXPIRED = "This link has expired or is not valid. Open IrisClick on the website again."

me_router = APIRouter(prefix="/me", tags=["desktop link"], route_class=DatabaseSafeRoute)
desktop_router = APIRouter(tags=["desktop link"], route_class=DatabaseSafeRoute)


class LinkTokenRead(BaseModel):
    link_token: str
    expires_at: int


class SessionRequest(BaseModel):
    link_token: str = Field(min_length=10, max_length=2000)


class LinkedUser(BaseModel):
    user_id: int
    full_name: str


class DesktopSessionRead(BaseModel):
    desktop_token: str
    expires_at: int
    user: LinkedUser


def _issue(kind: str, user_id: int) -> tuple[str, int]:
    try:
        return desktop_tokens.make(kind, user_id)
    except TokenError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@me_router.post("/desktop-link", response_model=LinkTokenRead)
def link_token(user: User = Depends(require_assistive)) -> LinkTokenRead:
    token, expires = _issue(LINK, user.user_id)
    return LinkTokenRead(link_token=token, expires_at=expires)


@desktop_router.post(SESSION_PATH, response_model=DesktopSessionRead)
def desktop_session(body: SessionRequest, request: Request, db: Session = Depends(get_db)) -> DesktopSessionRead:
    try:
        user_id = desktop_tokens.read(body.link_token, LINK)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=LINK_EXPIRED) from exc
    user = db.get(User, user_id)
    if user is None or user.role != ROLE_ASSISTIVE_USER or user.status != STATUS_ACTIVE:
        raise HTTPException(status_code=401, detail=LINK_EXPIRED)
    token, expires = _issue(DESKTOP, user.user_id)
    log_activity("desktop_linked", f"IrisClick Desktop linked for {user.full_name}", user.user_id, session=db)
    db.commit()
    return DesktopSessionRead(desktop_token=token, expires_at=expires,
                              user=LinkedUser(user_id=user.user_id, full_name=user.full_name))
