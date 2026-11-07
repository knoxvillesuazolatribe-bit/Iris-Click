from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, set_session_cookie
from app.config import get_settings
from app.schemas.auth import AssistiveSelectRequest, AssistiveTileRead, SessionUserRead
from app.services import assistive_service, session_service
from app.services.assistive_service import SelectionError

router = APIRouter(prefix="/assistive", tags=["assistive"], route_class=DatabaseSafeRoute)


@router.get("/users", response_model=list[AssistiveTileRead])
def list_users(db: Session = Depends(get_db)) -> list[AssistiveTileRead]:
    """Name tiles for the sign-in screen (no sign-in needed: it is the sign-in)."""
    tiles = assistive_service.list_tiles(db, get_settings().profiles_dir)
    return [AssistiveTileRead.model_validate(tile) for tile in tiles]


@router.post("/select", response_model=SessionUserRead)
def select_user(body: AssistiveSelectRequest, request: Request, response: Response,
                db: Session = Depends(get_db)) -> SessionUserRead:
    try:
        user = assistive_service.select_user(db, body.user_id)
    except SelectionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    session_service.revoke(db, request.cookies.get(session_service.COOKIE_NAME))
    token = session_service.create_session(db, user)
    db.commit()
    set_session_cookie(response, token, user.role)
    return SessionUserRead.model_validate(user)
