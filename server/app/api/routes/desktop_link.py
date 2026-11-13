"""IrisClick Desktop side of the web ↔ desktop link (runs on the user's PC).

The hosted website signs the user in, then hands this app a 5-minute link token
(POST /api/desktop/link). This app exchanges it with the hosted server
(IRISCLICK_CLOUD_URL + /api/desktop/session) for a 12-hour desktop token, saves
it on this PC, and makes that user the active user, so calibrations are saved
to the right person and the tracking worker uses their settings.

Only allowed websites reach this route (app/api/origin_guard.py). With no
IRISCLICK_CLOUD_URL set (today's local setup) the routes answer 503 and nothing
else changes.
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import SERVER_DIR, STORAGE_DIR
from app.services import active_user

logger = logging.getLogger("irisclick.desktop_link")

NOT_SET_UP = "IrisClick Desktop is not connected to the IrisClick website (IRISCLICK_CLOUD_URL is empty)."
CANNOT_REACH = "IrisClick Desktop could not reach the IrisClick website. Check the internet and try again."
SESSION_FILE = "desktop_session.json"
TIMEOUT_S = 15.0


class DesktopLinkSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=SERVER_DIR / ".env", env_file_encoding="utf-8", extra="ignore")
    irisclick_cloud_url: str = ""


def cloud_url() -> str:
    return DesktopLinkSettings().irisclick_cloud_url.strip().rstrip("/")


session_path: Path = STORAGE_DIR / SESSION_FILE  # replaced in tests


def _post_json(url: str, body: dict, timeout: float = TIMEOUT_S) -> tuple[int, dict]:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured site
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {}


post_json: Callable[[str, dict], tuple[int, dict]] = _post_json  # replaced in tests


def load_session() -> dict | None:
    """The saved, unexpired link, or None."""
    try:
        data = json.loads(session_path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("expires_at", 0) <= time.time():
        return None
    return data


_save_lock = threading.Lock()
SAVE_TRIES = 5


def _save_session(data: dict | None) -> None:
    """Write the link atomically. Several pages may link at the same moment: one writer at a time, each
    with its own temporary file, and a short retry because Windows refuses to replace a file another
    process is reading (found in testing: a 500 "Access is denied" when two links arrived together)."""
    with _save_lock:
        if data is None:
            session_path.unlink(missing_ok=True)
            return
        session_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = session_path.with_name(f"{session_path.stem}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        try:
            for attempt in range(SAVE_TRIES):
                try:
                    tmp.replace(session_path)
                    return
                except PermissionError:
                    if attempt == SAVE_TRIES - 1:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        finally:
            tmp.unlink(missing_ok=True)


router = APIRouter(prefix="/desktop", tags=["desktop link"])


class LinkRequest(BaseModel):
    link_token: str = Field(min_length=10, max_length=2000)


class LinkedUser(BaseModel):
    user_id: int
    full_name: str


class LinkStatus(BaseModel):
    connected_to_website: bool
    linked: bool
    user: LinkedUser | None = None


def _status() -> LinkStatus:
    session = load_session()
    user = LinkedUser.model_validate(session["user"]) if session else None
    return LinkStatus(connected_to_website=bool(cloud_url()), linked=user is not None, user=user)


@router.get("/link", response_model=LinkStatus)
def link_status() -> LinkStatus:
    return _status()


@router.post("/link", response_model=LinkStatus)
def link(body: LinkRequest) -> LinkStatus:
    base = cloud_url()
    if not base:
        raise HTTPException(status_code=503, detail=NOT_SET_UP)
    try:
        status, answer = post_json(f"{base}/api/desktop/session", {"link_token": body.link_token})
    except (OSError, ValueError) as exc:
        logger.warning("Website not reachable for linking: %s", exc)
        raise HTTPException(status_code=502, detail=CANNOT_REACH) from exc
    if status != 200:
        raise HTTPException(status_code=401 if status in (401, 403) else 502,
                            detail=answer.get("detail") if isinstance(answer.get("detail"), str) else CANNOT_REACH)
    try:
        user = LinkedUser.model_validate(answer["user"])
        session = {"desktop_token": str(answer["desktop_token"]), "expires_at": int(answer["expires_at"]),
                   "user": user.model_dump()}
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=CANNOT_REACH) from exc
    _save_session(session)
    active_user.set_user_id(user.user_id)
    logger.info("Linked to %s (user %s)", user.full_name, user.user_id)
    return _status()


@router.post("/unlink", response_model=LinkStatus)
def unlink() -> LinkStatus:
    session = load_session()
    _save_session(None)
    if session:
        active_user.clear_if(int(session["user"]["user_id"]))
    return _status()
