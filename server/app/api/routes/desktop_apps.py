"""Apps for the hosted website, served by IrisClick Desktop (127.0.0.1).

The hosted website keeps each person's app tiles, but it cannot open a program on this
PC. Its Apps tiles ask these routes instead (only IrisClick's own websites pass the
Origin guard, app/api/origin_guard.py):

    GET  /api/desktop/apps/available   this PC's Start-menu programs (Edit Apps > Add)
    POST /api/desktop/apps/open        open one built-in app or Start-menu program

Safety: nothing a request names is run as such. A built-in app is looked up in the fixed
list (app/services/apps_service.py); a program must be a .lnk/.exe found by this PC's own
Start-menu scan. Opening needs a person linked on this PC (desktop_link).
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.routes.desktop_tracking import _db, linked_user
from app.services import apps_service, user_apps_service
from app.services.apps_service import AppError
from app.services.system_log_service import log_activity

logger = logging.getLogger("irisclick.desktop_apps")

NOT_HERE = "That program isn't installed on this computer."

router = APIRouter(tags=["desktop apps"])


class OpenRequest(BaseModel):
    kind: Literal["builtin", "installed_app"]
    key: str | None = Field(default=None, max_length=40)
    path: str | None = Field(default=None, max_length=1024)


@router.get("/desktop/apps/available")
def available() -> list[dict]:
    return [{"name": a.name, "path": a.path} for a in user_apps_service.installed_apps()]


def open_program(path: str) -> str:
    """Opens a Start-menu program of this PC; returns its name. Raises HTTPException."""
    from pathlib import Path
    if Path(path).suffix.lower() not in user_apps_service.ALLOWED_APP_TYPES:
        raise HTTPException(status_code=422, detail="That program cannot be opened from IrisClick.")
    found = user_apps_service._scanned(path)  # noqa: SLF001 - the same check the PC's own tiles use
    if found is None or not user_apps_service.file_exists(found.path):
        raise HTTPException(status_code=404, detail=NOT_HERE)
    try:
        apps_service.opener(found.path)
    except OSError as exc:
        logger.warning("Could not open %s: %s", found.name, exc)
        raise HTTPException(status_code=500, detail=f"{found.name} could not be opened on this computer.") from exc
    return found.name


@router.post("/desktop/apps/open")
def open_app(body: OpenRequest, db: Session = Depends(_db)) -> dict:
    user = linked_user(db)
    if body.kind == "builtin":
        try:
            label = apps_service.launch(body.key or "").label
        except AppError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    else:
        label = open_program(body.path or "")
    log_activity("app_launched", f"{user.full_name} opened {label}", user.user_id, session=db)
    db.commit()
    return {"launched": True, "label": label}
