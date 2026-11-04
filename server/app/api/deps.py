"""Shared pieces for the account routes: sign-in checks and database errors."""

from collections.abc import Callable, Iterator

from fastapi import Depends, HTTPException, Request, Response
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import database
from app.models.user import ROLE_ADMIN, ROLE_ASSISTIVE_USER, User
from app.services import session_service
from app.services.session_service import SignedIn

DATABASE_UNAVAILABLE = ("The IrisClick database cannot be reached right now. Eye tracking "
                        "still works; try again in a moment.")


class DatabaseSafeRoute(APIRoute):
    """Turns a database failure into a clear 503 instead of a bare 500."""

    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)
            except SQLAlchemyError as exc:
                raise HTTPException(status_code=503, detail=DATABASE_UNAVAILABLE) from exc

        return guarded


def get_db() -> Iterator[Session]:
    session = database.get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def current_sign_in(request: Request, db: Session = Depends(get_db)) -> SignedIn | None:
    return session_service.resolve(db, request.cookies.get(session_service.COOKIE_NAME))


def require_signed_in(signed_in: SignedIn | None = Depends(current_sign_in)) -> SignedIn:
    if signed_in is None:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return signed_in


def require_admin(signed_in: SignedIn = Depends(require_signed_in)) -> User:
    if signed_in.user.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Administrators only.")
    return signed_in.user


def require_assistive(signed_in: SignedIn = Depends(require_signed_in)) -> User:
    if signed_in.user.role != ROLE_ASSISTIVE_USER:
        raise HTTPException(status_code=403, detail="Pick your name on the sign-in screen first.")
    return signed_in.user


def set_session_cookie(response: Response, token: str, role: str) -> None:
    response.set_cookie(
        session_service.COOKIE_NAME, token,
        max_age=session_service.session_max_age_s(role),
        path=session_service.COOKIE_PATH,
        httponly=True, samesite="lax", secure=False,  # served over http://localhost only
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(session_service.COOKIE_NAME, path=session_service.COOKIE_PATH,
                           httponly=True, samesite="lax")
