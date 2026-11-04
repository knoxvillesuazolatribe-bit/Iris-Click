"""Loads the signed-in user's accessibility settings when tracking starts (hook H4d).

Falls back to the .env settings, unchanged, when nobody is signed in, the
user has never saved settings, the database does not answer within
TIMEOUT_S, or anything else goes wrong: tracking must always start.
"""

import logging
import threading

from app.config import Settings
from app.models import database
from app.services import accessibility_service, active_user

logger = logging.getLogger("irisclick.worker.settings")

TIMEOUT_S = 3.0


def _load(user_id: int, result: dict) -> None:
    try:
        with database.get_session_factory()() as db:
            result["overrides"] = accessibility_service.worker_overrides(db, user_id)
    except Exception as exc:  # noqa: BLE001
        result["error"] = exc


def for_active_user(settings: Settings, timeout_s: float = TIMEOUT_S) -> Settings:
    user_id = active_user.read_from_disk()
    if user_id is None:
        logger.info("No one signed in: using the standard settings")
        return settings
    result: dict = {}
    thread = threading.Thread(target=_load, args=(user_id, result), daemon=True,
                              name="user-settings")
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        logger.warning("Settings for user %s took over %.0f s: using the standard settings",
                       user_id, timeout_s)
        return settings
    if "error" in result:
        logger.warning("Settings for user %s not loaded (%s): using the standard settings",
                       user_id, result["error"])
        return settings
    overrides = result.get("overrides")
    if not overrides:
        logger.info("User %s has the standard settings", user_id)
        return settings
    logger.info("Using user %s's accessibility settings: %s", user_id, overrides)
    return settings.model_copy(update=overrides)
