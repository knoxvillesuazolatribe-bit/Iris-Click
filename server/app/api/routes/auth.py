from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import (
    DatabaseSafeRoute,
    clear_session_cookie,
    get_db,
    require_signed_in,
    set_session_cookie,
)
from app.models.user import ROLE_ASSISTIVE_USER
from app.schemas.auth import AdminLoginRequest, SessionUserRead
from app.services import active_user, session_service
from app.services.auth_service import AuthError, authenticate_admin
from app.services.session_service import SignedIn
from app.services.system_log_service import log_activity

router = APIRouter(prefix="/auth", tags=["auth"], route_class=DatabaseSafeRoute)


@router.get("/me", response_model=SessionUserRead)
def me(signed_in: SignedIn = Depends(require_signed_in)) -> SessionUserRead:
    return SessionUserRead.model_validate(signed_in.user)


@router.post("/admin/login", response_model=SessionUserRead)
def admin_login(body: AdminLoginRequest, request: Request, response: Response,
                db: Session = Depends(get_db)) -> SessionUserRead:
    try:
        user = authenticate_admin(db, body.email, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    # One session per browser: signing in replaces whoever was signed in here.
    session_service.revoke(db, request.cookies.get(session_service.COOKIE_NAME))
    token = session_service.create_session(db, user)
    db.commit()
    set_session_cookie(response, token, user.role)
    return SessionUserRead.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    token = request.cookies.get(session_service.COOKIE_NAME)
    signed_in = session_service.resolve(db, token)
    session_service.revoke(db, token)
    if signed_in is not None:
        user = signed_in.user
        log_activity("logout", f"{user.full_name} signed out", user.user_id, session=db)
        if user.role == ROLE_ASSISTIVE_USER:
            # Tracking keeps running: a hands-free user who signs out must
            # still be able to look and wink to pick their name again.
            active_user.clear_if(user.user_id)
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    clear_session_cookie(response)
    return response
