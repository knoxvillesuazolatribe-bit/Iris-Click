"""Keeps IrisClick Desktop's small local database in step with the hosted server.

The installed desktop app has no Supabase password: DB_HOST is empty, so the
existing code (calibration results, the worker's user settings, screenshot logs)
uses the local SQLite file exactly as it already can. This module connects that
file to the hosted server with the desktop token from the web ↔ desktop link:

  pull  the linked user, their accessibility settings and the admin's global
        defaults (what accessibility_service.worker_overrides reads)
  push  new calibration results and calibration/screenshot activity logs, which the
        hosted server saves to Supabase for the admin's logs and reports

Offline, rows wait on the PC and are sent later. Desktop mode is on only when
IRISCLICK_CLOUD_URL is set and DB_HOST is empty; otherwise nothing here runs.
"""

import hashlib
import json
import logging
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import delete, select

import app.models.all_models  # noqa: F401  (registers every table)
from app.api.routes import desktop_link
from app.config import STORAGE_DIR, get_settings
from app.models import database
from app.models.accessibility_settings import AccessibilitySettings
from app.models.base import Base
from app.models.calibration_record import CalibrationRecord
from app.models.system_log import SystemLog
from app.models.system_settings import SystemSettings
from app.models.timestamps import as_utc
from app.models.user import User

logger = logging.getLogger("irisclick.desktop_sync")

SYNCED_LOG_TYPES = ("calibration", "calibration_failed", "screenshot")
BATCH = 50
TIMEOUT_S = 20.0
state_path: Path = STORAGE_DIR / "desktop_sync_state.json"  # replaced in tests


class LinkExpired(Exception):
    """The hosted server refused the desktop token: the user must be linked again."""


def desktop_mode() -> bool:
    return bool(desktop_link.cloud_url()) and not get_settings().uses_postgres


# --- local database ----------------------------------------------------------------------------

def schema_fingerprint() -> str:
    shape = sorted((t.name, sorted(c.name for c in t.columns)) for t in Base.metadata.sorted_tables)
    return hashlib.sha256(json.dumps(shape).encode()).hexdigest()[:16]


def _load_state() -> dict:
    try:
        data = json.loads(state_path.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(state_path)


def prepare_local_db() -> None:
    """Creates the local tables; after an update that changes them, sends what is
    waiting first, then starts a fresh local copy (it is only a cache)."""
    engine = database.get_engine()
    state = _load_state()
    fingerprint = schema_fingerprint()
    if state.get("schema") not in (None, fingerprint):
        try:
            sync_once()
        except Exception:  # noqa: BLE001 - offline: those rows cannot be sent anyway
            logger.warning("Could not send waiting rows before refreshing the local database")
        Base.metadata.drop_all(engine)
        state = {}
    Base.metadata.create_all(engine)
    state["schema"] = fingerprint
    _save_state(state)


# --- hosted server -----------------------------------------------------------------------------

def _http(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{desktop_link.cloud_url()}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 - configured site
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {}


http: Callable[..., tuple[int, dict]] = _http  # replaced in tests


def _call(method: str, path: str, token: str, body: dict | None = None) -> dict:
    status, data = http(method, path, token, body)
    if status == 401:
        raise LinkExpired(data.get("detail", "Link expired"))
    if status != 200:
        raise OSError(f"{method} {path} answered {status}")
    return data


def pull(token: str) -> dict:
    profile = _call("GET", "/api/desktop/profile", token)
    user = profile["user"]
    with database.get_session_factory()() as db:
        db.merge(User(user_id=user["user_id"], full_name=user["full_name"], role=user["role"],
                      status=user["status"]))
        db.flush()  # the user row first: settings rows point at it
        db.execute(delete(AccessibilitySettings).where(AccessibilitySettings.user_id == user["user_id"]))
        if profile.get("accessibility"):
            db.add(AccessibilitySettings(user_id=user["user_id"], **profile["accessibility"]))
        db.execute(delete(SystemSettings))
        if profile.get("global_defaults"):
            db.add(SystemSettings(setting_id=1, **profile["global_defaults"]))
        db.commit()
    return profile


def _calibration_json(row: CalibrationRecord) -> dict:
    return {
        "profile_file_id": row.profile_file_id, "profile_name": row.profile_name or "",
        "status": row.status,
        "accuracy_score": float(row.accuracy_score) if row.accuracy_score is not None else None,
        "error_fraction": row.error_fraction, "low_accuracy": row.low_accuracy,
        "feature_source": row.feature_source, "camera_index": row.camera_index,
        "sample_count": row.sample_count, "calibration_data": row.calibration_data,
        "failure_reason": row.failure_reason,
        "calibration_date": as_utc(row.calibration_date).isoformat(),
    }


def push(token: str, user_id: int) -> dict:
    """Sends rows newer than the last sent ones; returns how many went out."""
    state = _load_state()
    sent = {"calibrations": 0, "logs": 0}
    with database.get_session_factory()() as db:
        while True:
            rows = db.scalars(select(CalibrationRecord)
                              .where(CalibrationRecord.calibration_id > state.get("calibration_id", 0))
                              .order_by(CalibrationRecord.calibration_id).limit(BATCH)).all()
            if not rows:
                break
            mine = [_calibration_json(r) for r in rows if r.user_id == user_id]
            if mine:
                _call("POST", "/api/desktop/calibrations", token, {"records": mine})
            sent["calibrations"] += len(mine)
            state["calibration_id"] = rows[-1].calibration_id
            _save_state(state)
        while True:
            logs = db.scalars(select(SystemLog)
                              .where(SystemLog.log_id > state.get("log_id", 0))
                              .order_by(SystemLog.log_id).limit(BATCH)).all()
            if not logs:
                break
            mine = [{"activity_type": l.activity_type, "activity_description": l.activity_description,
                     "log_date": as_utc(l.log_date).isoformat()}
                    for l in logs if l.user_id == user_id and l.activity_type in SYNCED_LOG_TYPES]
            if mine:
                _call("POST", "/api/desktop/logs", token, {"logs": mine})
            sent["logs"] += len(mine)
            state["log_id"] = logs[-1].log_id
            _save_state(state)
    return sent


def sync_once() -> dict:
    """One pull + push for the linked user. Never raises for network trouble."""
    if not desktop_mode():
        return {"status": "off"}
    session = desktop_link.load_session()
    if session is None:
        return {"status": "not_linked"}
    token, user_id = session["desktop_token"], int(session["user"]["user_id"])
    try:
        pull(token)
        sent = push(token, user_id)
    except LinkExpired:
        logger.info("Desktop link expired; waiting for the user to choose their name again")
        return {"status": "link_expired"}
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("Sync postponed: %s", exc)
        return {"status": "offline"}
    return {"status": "ok", **sent}


def run_forever(stop: threading.Event, every_s: float = 60.0, linked_every_s: float = 5.0) -> None:
    """Background loop for the launcher: syncs every minute, and within seconds of a new link."""
    last_token = None
    while not stop.is_set():
        session = desktop_link.load_session()
        token = session["desktop_token"] if session else None
        result = sync_once()
        changed = token != last_token
        last_token = token
        stop.wait(linked_every_s if changed or result["status"] in ("not_linked", "link_expired") else every_s)
