"""Gaze Tracking for the hosted website, served by IrisClick Desktop (hybrid item 6).

The hosted website cannot see this PC's tracker, so its Gaze Tracking page talks
to these routes on 127.0.0.1 (only allowed websites: origin_guard). They act for
the user linked from the website (desktop_link) and reuse the existing Home logic
(home_service.tracking_view / start_tracking / stop_tracking), so the rules are
the same as on the PC: the user's own latest calibration on this computer.

    GET  /api/desktop/tracking         the tracking view (same shape as /api/me/tracking)
    POST /api/desktop/tracking/start   start with the user's own calibration
    POST /api/desktop/tracking/stop
    WS   /api/ws/tracking              the same view every second (no polling)
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.routes import desktop_link
from app.config import get_settings
from app.models import database
from app.models.user import User
from app.schemas.home import TrackingViewRead
from app.services import home_service
from app.services.home_service import HomeError
from app.services.tracking_service import get_tracking_service

logger = logging.getLogger("irisclick.desktop_tracking")

NOT_LINKED = "Choose your name on the IrisClick website first."
NOT_READY = "IrisClick Desktop is still getting your details from the website. Try again in a moment."
PUSH_EVERY_S = 1.0

router = APIRouter(tags=["desktop tracking"])


def _db():
    session = database.get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def linked_user(db: Session) -> User:
    session = desktop_link.load_session()
    if session is None:
        raise HTTPException(status_code=409, detail=NOT_LINKED)
    user = db.get(User, int(session["user"]["user_id"]))
    if user is None:  # desktop mode: the sync has not copied the user yet
        raise HTTPException(status_code=409, detail=NOT_READY)
    return user


def _view(db: Session) -> dict:
    user = linked_user(db)
    view = home_service.tracking_view(db, user, get_settings(), get_tracking_service())
    return TrackingViewRead.model_validate(view, from_attributes=True).model_dump(mode="json")


@router.get("/desktop/tracking")
def tracking(db: Session = Depends(_db)) -> dict:
    return _view(db)


@router.post("/desktop/tracking/start")
def start(db: Session = Depends(_db)) -> dict:
    user = linked_user(db)
    try:
        view = home_service.start_tracking(db, user, get_settings(), get_tracking_service())
    except HomeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return TrackingViewRead.model_validate(view, from_attributes=True).model_dump(mode="json")


@router.post("/desktop/tracking/stop")
def stop(db: Session = Depends(_db)) -> dict:
    user = linked_user(db)
    view = home_service.stop_tracking(db, user, get_settings(), get_tracking_service())
    return TrackingViewRead.model_validate(view, from_attributes=True).model_dump(mode="json")


def _snapshot() -> dict:
    with database.get_session_factory()() as db:
        try:
            return {"ok": True, "view": _view(db)}
        except HTTPException as exc:
            return {"ok": False, "detail": exc.detail}


@router.websocket("/ws/tracking")
async def tracking_socket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(await run_in_threadpool(_snapshot))
            await asyncio.sleep(PUSH_EVERY_S)
    except (WebSocketDisconnect, RuntimeError):
        return
