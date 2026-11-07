"""Admin view and editing of one assistive user's Apps tiles (extension)."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_admin
from app.api.routes.user_apps import apply_update, fail
from app.models.user import User
from app.schemas.user_apps import InstalledAppRead, TileAdd, TilesRead, TileUpdate
from app.services import admin_service, user_apps_service
from app.services.admin_service import AdminError
from app.services.apps_service import AppError

router = APIRouter(prefix="/admin/users", tags=["admin"], route_class=DatabaseSafeRoute)


def _target(db: Session, user_id: int) -> User:
    try:
        return admin_service.assistive_user(db, user_id)
    except AdminError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{user_id}/apps", response_model=TilesRead)
def tiles(user_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return user_apps_service.overview(db, _target(db, user_id))


@router.post("/{user_id}/apps", response_model=TilesRead, status_code=201)
def add_tile(user_id: int, body: TileAdd, db: Session = Depends(get_db),
             admin: User = Depends(require_admin)):
    user = _target(db, user_id)
    try:
        user_apps_service.add(db, user, body.model_dump(), actor=admin)
    except AppError as exc:
        fail(exc)
    return user_apps_service.overview(db, user)


@router.patch("/{user_id}/apps/{tile_id}", response_model=TilesRead)
def update_tile(user_id: int, tile_id: int, body: TileUpdate, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = _target(db, user_id)
    try:
        apply_update(db, user, tile_id, body, actor=admin)
    except AppError as exc:
        fail(exc)
    return user_apps_service.overview(db, user)


@router.delete("/{user_id}/apps/{tile_id}", status_code=204)
def remove_tile(user_id: int, tile_id: int, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    try:
        user_apps_service.remove(db, _target(db, user_id), tile_id, actor=admin)
    except AppError as exc:
        fail(exc)
    return Response(status_code=204)


@router.post("/{user_id}/apps/reset", response_model=TilesRead)
def reset_tiles(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = _target(db, user_id)
    user_apps_service.reset(db, user, actor=admin)
    return user_apps_service.overview(db, user)


@router.get("/{user_id}/apps/available", response_model=list[InstalledAppRead])
def available(user_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    _target(db, user_id)
    return [InstalledAppRead(name=a.name, path=a.path) for a in user_apps_service.installed_apps()]
