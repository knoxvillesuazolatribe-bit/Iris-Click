"""The online copy's server (Vercel). The PC server in app/api/main.py is unchanged.

create_app() builds the FastAPI app: the account and extension routes the PC
server has, minus calibration, cameras, the tracking worker and the
calibration websocket (they need the user's webcam and Windows). Starting
tracking or opening a PC app answers PC_ONLY instead.

configure_runtime() is called once by api/index.py before the app is built:
Vercel only allows writing under /tmp, runs many short-lived copies of the
server (so database connections are not kept open), and may freeze a request's
background threads once the response is sent (so SOS sends during the request).
"""

import logging
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.api.deps import DatabaseSafeRoute, get_db, require_assistive
from app.cloud import access
from app.cloud import desktop as cloud_desktop
from app.config import get_settings
from app.models import database
from app.models.user import User
from app.schemas.home import HomeRead, TrackingViewRead
from app.schemas.tracking import WorkerStatusRead
from app.services import accessibility_service, home_service

logger = logging.getLogger("irisclick.cloud")

PC_ONLY_TRACKING = ("Eye tracking only works on the IrisClick PC. This is the online copy: "
                    "Voice, SOS and Settings still work here.")
PC_ONLY_APPS = "Opening apps only works on the IrisClick PC. This is the online copy."
# SOS sends inside the request here, so retries are shorter than on the PC (10/30/60 s).
SOS_RETRY_DELAYS_S = (5.0, 15.0)
# Vercel's rewrite passes the original path in this query parameter (see vercel.json).
PATH_PARAM = "__irisclick_path"
# Settings paths that point into server/app/storage on the PC.
STORAGE_SETTINGS = {
    "DEVICE_SETTINGS_PATH": "device_settings.json",
    "FACE_MODEL_PATH": "face_landmarker.task",
    "PROFILES_DIR": "calibration_profiles",
    "RECENTER_PATH": "recenter.json",
    "WORKER_PID_PATH": "tracking_worker.pid",
    "WORKER_LOG_PATH": "tracking_worker.log",
    "SCREENSHOTS_DIR": "screenshots",
}


class NoTrackingHere:
    """Stands in for the PC's tracking service: there is no tracker online."""

    def status(self) -> WorkerStatusRead:
        return WorkerStatusRead(running=False)


pc_only = APIRouter(prefix="/me", tags=["online copy"], route_class=DatabaseSafeRoute)


@pc_only.get("/home", response_model=HomeRead)
def home(user: User = Depends(require_assistive), db: Session = Depends(get_db)) -> HomeRead:
    settings = accessibility_service.effective(db, user, get_settings())
    return HomeRead(full_name=user.full_name, gestures=home_service.gesture_guide(settings))


@pc_only.get("/tracking", response_model=TrackingViewRead)
def tracking(user: User = Depends(require_assistive), db: Session = Depends(get_db)) -> TrackingViewRead:
    view = home_service.tracking_view(db, user, get_settings(), NoTrackingHere())
    return TrackingViewRead.model_validate(view, from_attributes=True)


@pc_only.post("/tracking/start")
@pc_only.post("/tracking/stop")
@pc_only.post("/tracking/restart")
def tracking_change(_user: User = Depends(require_assistive)):
    raise HTTPException(status_code=409, detail=PC_ONLY_TRACKING)


@pc_only.post("/apps/{app_id}/launch")
def launch(_user: User = Depends(require_assistive)):
    raise HTTPException(status_code=409, detail=PC_ONLY_APPS)


@pc_only.post("/apps/tiles/{tile_id}/launch")
def launch_tile(tile_id: int, user: User = Depends(require_assistive), db: Session = Depends(get_db)) -> dict:
    """Websites need no PC: their address goes back to the page, which opens it in a
    new tab on the user's own device. Programs (Word, Calculator, ...) stay PC-only."""
    from app.models.user_app_shortcut import KIND_BUILTIN, KIND_WEBSITE, UserAppShortcut
    from app.services import apps_service
    from app.services.system_log_service import log_activity
    from app.services.user_apps_service import UserAppsError, clean_url

    row = db.get(UserAppShortcut, tile_id)
    if row is None or row.user_id != user.user_id or not row.is_visible:
        raise HTTPException(status_code=404, detail="That app is not in your apps.")
    url = None
    if row.type == KIND_WEBSITE:
        try:
            url = clean_url(row.target or "")
        except UserAppsError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    elif row.type == KIND_BUILTIN:
        app = next((a for a in apps_service.available() if a.app_id == row.builtin_key), None)
        if app is not None and app.target.startswith(("https://", "http://")):
            url = app.target  # Browser (Google) and Calendar (website)
    if url is None:
        raise HTTPException(status_code=409, detail=PC_ONLY_APPS)
    log_activity("app_launched", f"{user.full_name} opened {row.label} (online)", user.user_id, session=db)
    db.commit()
    return {"launched": True, "label": row.label, "url": url}


CHECKED_SETTINGS = ("IRISCLICK_ACCESS_CODE", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER",
                    "DB_PASSWORD", "DB_SSLMODE", "SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD",
                    "SMTP_FROM")

setup_check = APIRouter(prefix="/cloud", tags=["online copy"])


@setup_check.get("/check")
def check_setup() -> dict:
    """Which settings this deployment has (set/missing, never values) and whether the
    database answers, with the driver's reason when it does not. Behind the access code."""
    settings = get_settings()
    report = {
        "build": {"environment": os.environ.get("VERCEL_ENV", "local"),
                  "branch": os.environ.get("VERCEL_GIT_COMMIT_REF", ""),
                  "commit": os.environ.get("VERCEL_GIT_COMMIT_SHA", "")[:7]},
        "settings": {name: "set" if os.environ.get(name, "").strip() else "missing"
                     for name in CHECKED_SETTINGS},
        "db_port": settings.db_port,
        "database": "ok",
        "error": None,
    }
    try:
        database.check_connection()
    except Exception as exc:  # noqa: BLE001 - reported to the admin, never raised
        reason = str(getattr(exc, "orig", None) or exc).strip().splitlines()
        text = f"{type(getattr(exc, 'orig', None) or exc).__name__}: {reason[0] if reason else ''}"
        for secret in (settings.db_password.get_secret_value(), settings.smtp_password.get_secret_value()):
            if secret:
                text = text.replace(secret, "***")
        report.update(database="error", error=text[:300])
    return report


def _routers() -> list[APIRouter]:
    from app.api.routes import (accessibility, admin_reports, admin_settings, admin_speech,
                                admin_user_apps, admin_users, admin_voice_settings,
                                admin_word_filter, apps, assistive, auth, health, neural_tts,
                                sos, speech, user_apps, voice, word_filter)
    # pc_only first: its paths win over the PC versions in apps/user_apps.
    return [access.router, setup_check, pc_only, health.router, auth.router, assistive.router,
            admin_users.router, voice.router, sos.router, accessibility.router,
            admin_settings.router, admin_settings.public, admin_reports.router, apps.router,
            user_apps.router, admin_user_apps.router, word_filter.router,
            admin_word_filter.router, speech.router, admin_speech.router, neural_tts.router,
            admin_voice_settings.router, cloud_desktop.me_router, cloud_desktop.desktop_router]


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # No /docs on the internet; the site and the API share one origin, so no CORS.
    app = FastAPI(title=f"{settings.app_name} (online copy)", debug=False,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.middleware("http")(access.gate(settings.api_prefix))
    for router in _routers():
        app.include_router(router, prefix=settings.api_prefix)
    return app


# --- Vercel runtime ---------------------------------------------------------------------------

@lru_cache
def cloud_engine() -> Engine:
    """No connection pool (each server copy is short-lived) and no prepared statements, so
    Supabase's transaction pooler (port 6543) works too."""
    settings = get_settings()
    if not settings.uses_postgres:
        return database.enable_sqlite_foreign_keys(
            create_engine(settings.database_url, connect_args={"check_same_thread": False}))
    engine = create_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": database.CONNECT_TIMEOUT_S, "prepare_threshold": None},
    )
    return engine.execution_options(schema_translate_map={None: settings.db_schema})


def assume_pc_apps() -> None:
    """The user's apps are on their IrisClick PC, not on this Linux server, so the
    online copy shows every default app (Calculator, Word, Excel, PowerPoint)
    instead of hiding the ones the server lacks. Opening one answers PC_ONLY_APPS."""
    from app.services import apps_service

    apps_service.finder["calculator"] = lambda: "calc.exe"
    apps_service.finder["app_path"] = lambda exe: exe


def configure_runtime(storage_dir: Path) -> None:
    from app.services import active_user, neural_tts_service
    from app.services.sos_dispatcher import dispatcher

    assume_pc_apps()

    for name, leaf in STORAGE_SETTINGS.items():
        os.environ.setdefault(name, str(storage_dir / leaf))
    get_settings.cache_clear()
    active_user.use_path(storage_dir / "active_user.json")
    neural_tts_service.cache_dir = storage_dir / "tts_cache"
    database.get_engine = cloud_engine
    database.get_session_factory.cache_clear()
    dispatcher.inline = True
    dispatcher.delays = SOS_RETRY_DELAYS_S


class VercelPaths:
    """Restores the request path from vercel.json's rewrite and marks cookies Secure on HTTPS."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        scope = dict(scope)
        query = parse_qsl(scope.get("query_string", b"").decode("latin-1"), keep_blank_values=True)
        original = [value for key, value in query if key == PATH_PARAM]
        if original:
            path = "/api/" + original[0].lstrip("/")
            scope["path"] = path
            scope["raw_path"] = path.encode("utf-8")
            rest = [(key, value) for key, value in query if key != PATH_PARAM]
            scope["query_string"] = urlencode(rest).encode("latin-1")
        headers = dict(scope.get("headers") or [])
        https = (headers.get(b"x-forwarded-proto", b"").split(b",")[0].strip() == b"https"
                 or scope.get("scheme") == "https")

        async def send_secure(message):
            if https and message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = [
                    (key, value + b"; Secure")
                    if key.lower() == b"set-cookie" and b"secure" not in value.lower() else (key, value)
                    for key, value in message.get("headers", [])
                ]
            await send(message)

        await self.app(scope, receive, send_secure)
