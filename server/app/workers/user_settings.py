"""Loads accessibility settings when tracking starts (hook H4d).

Order: the signed-in user's own settings → the admin's global defaults
(Phase 8) → server/.env. Falls back to .env, unchanged, when nothing is
saved, the database does not answer within TIMEOUT_S, or anything else goes
wrong: tracking must always start.
"""

import logging
import threading

from app.config import Settings
from app.models import database
from app.services import accessibility_service, active_user

logger = logging.getLogger("irisclick.worker.settings")

TIMEOUT_S = 3.0


def _load(user_id: int | None, env: Settings, result: dict) -> None:
    try:
        with database.get_session_factory()() as db:
            result["overrides"] = accessibility_service.worker_overrides(db, user_id, env)
    except Exception as exc:  # noqa: BLE001
        result["error"] = exc


def for_active_user(settings: Settings, timeout_s: float = TIMEOUT_S) -> Settings:
    user_id = active_user.read_from_disk()
    who = f"user {user_id}" if user_id is not None else "no one signed in"
    result: dict = {}
    thread = threading.Thread(target=_load, args=(user_id, settings, result), daemon=True,
                              name="user-settings")
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        logger.warning("Settings (%s) took over %.0f s: using the standard settings",
                       who, timeout_s)
        return settings
    if "error" in result:
        logger.warning("Settings (%s) not loaded (%s): using the standard settings",
                       who, result["error"])
        return settings
    overrides = result.get("overrides")
    if not overrides:
        logger.info("Settings (%s): the computer's standard settings", who)
        return settings
    logger.info("Settings (%s): %s", who, overrides)
    return settings.model_copy(update=overrides)
