"""Customizable Apps tiles for the signed-in assistive user (extension).

The Phase 9 endpoints (GET /me/apps, POST /me/apps/{app_id}/launch) stay as
they are; these live under /me/apps/tiles and /me/apps/available.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_assistive
from app.models.user import User
from app.schemas.user_apps import InstalledAppRead, LaunchRead, TileAdd, TilesRead, TileUpdate
from app.services import user_apps_service
from app.services.apps_service import AppError

router = APIRouter(prefix="/me/apps", tags=["apps"], route_class=DatabaseSafeRoute)


def fail(exc: AppError):
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def apply_update(db: Session, user: User, tile_id: int, body: TileUpdate, actor: User | None = None) -> None:
    if body.is_visible is not None:
        user_apps_service.set_visible(db, user, tile_id, body.is_visible, actor)
    if body.position is not None:
        user_apps_service.move(db, user, tile_id, body.position, actor)


@router.get("/tiles", response_model=TilesRead)
def tiles(user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    return user_apps_service.overview(db, user)


@router.post("/tiles", response_model=TilesRead, status_code=201)
def add_tile(body: TileAdd, user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    try:
        user_apps_service.add(db, user, body.model_dump())
    except AppError as exc:
        fail(exc)
    return user_apps_service.overview(db, user)


@router.patch("/tiles/{tile_id}", response_model=TilesRead)
def update_tile(tile_id: int, body: TileUpdate, user: User = Depends(require_assistive),
                db: Session = Depends(get_db)):
    try:
        apply_update(db, user, tile_id, body)
    except AppError as exc:
        fail(exc)
    return user_apps_service.overview(db, user)


@router.delete("/tiles/{tile_id}", status_code=204)
def remove_tile(tile_id: int, user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    try:
        user_apps_service.remove(db, user, tile_id)
    except AppError as exc:
        fail(exc)
    return Response(status_code=204)


@router.post("/tiles/reset", response_model=TilesRead)
def reset_tiles(user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    user_apps_service.reset(db, user)
    return user_apps_service.overview(db, user)


@router.get("/available", response_model=list[InstalledAppRead])
def available(_user: User = Depends(require_assistive)):
    return [InstalledAppRead(name=a.name, path=a.path) for a in user_apps_service.installed_apps()]


@router.post("/tiles/{tile_id}/launch", response_model=LaunchRead)
def launch_tile(tile_id: int, user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    """By tile id only: the target is read from the database, never the request."""
    try:
        label = user_apps_service.launch(db, user, tile_id)
    except AppError as exc:
        fail(exc)
    return LaunchRead(launched=True, label=label)
