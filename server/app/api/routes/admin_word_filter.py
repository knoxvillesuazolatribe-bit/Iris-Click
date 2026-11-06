"""Admin: Manage Settings > Word Filter (extension of Screens 25–28)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_admin
from app.models.user import User
from app.schemas.word_filter import (
    FilterSettingsRead, FilterSettingsWrite, ImportRead, ImportRequest, WordCreate, WordRead,
)
from app.services import word_filter_service as service
from app.services.word_filter_service import WordFilterError

router = APIRouter(prefix="/admin/word-filter", tags=["admin"], route_class=DatabaseSafeRoute)


def _fail(exc: WordFilterError):
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/settings", response_model=FilterSettingsRead)
def settings(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return service.get_settings(db)


@router.put("/settings", response_model=FilterSettingsRead)
def update_settings(body: FilterSettingsWrite, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    try:
        return service.update_settings(db, admin, body.enabled, body.tts_mode)
    except WordFilterError as exc:
        _fail(exc)


@router.get("/words", response_model=list[WordRead])
def words(q: str | None = Query(None, max_length=100), language: str | None = None,
          type: str | None = None, status: Literal["active", "removed", "all"] = "active",
          db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return service.list_words(db, q, language, type, status)


@router.post("/words", response_model=WordRead, status_code=201)
def add_word(body: WordCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    try:
        return service.add_word(db, admin, body.word, body.language, body.type)
    except WordFilterError as exc:
        _fail(exc)


@router.delete("/words/{word_id}", response_model=WordRead)
def remove_word(word_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Soft delete: the word can be restored."""
    try:
        return service.set_active(db, admin, word_id, False)
    except WordFilterError as exc:
        _fail(exc)


@router.post("/words/{word_id}/restore", response_model=WordRead)
def restore_word(word_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    try:
        return service.set_active(db, admin, word_id, True)
    except WordFilterError as exc:
        _fail(exc)


@router.post("/import", response_model=ImportRead)
def import_words(body: ImportRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    try:
        result = service.import_words(db, admin, body.content)
    except WordFilterError as exc:
        _fail(exc)
    return ImportRead(added=result.added, restored=result.restored, skipped=result.skipped)


@router.get("/export")
def export_words(format: Literal["txt", "csv"] = "csv", db: Session = Depends(get_db),
                 admin: User = Depends(require_admin)):
    text, name = service.export_words(db, admin, format)
    media = "text/csv" if format == "csv" else "text/plain"
    return Response(content=text.encode("utf-8"), media_type=f"{media}; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
