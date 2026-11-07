"""System_Logs writer: one row for every user action that matters.

A log row must never break the action it records, so log_activity() catches
every error, logs it and returns False.
"""

import logging

from sqlalchemy.orm import Session

from app.models import database
from app.models.system_log import SystemLog

logger = logging.getLogger("irisclick.system_log")

DESCRIPTION_MAX_CHARS = 2000


def build_log(activity_type: str, description: str | None = None,
              user_id: int | None = None) -> SystemLog:
    if description is not None:
        description = description[:DESCRIPTION_MAX_CHARS]
    return SystemLog(user_id=user_id, activity_type=activity_type[:100],
                     activity_description=description)


def log_activity(activity_type: str, description: str | None = None,
                 user_id: int | None = None, *, session: Session | None = None) -> bool:
    """Write one System_Logs row; True when written (or added to ``session``).

    With ``session`` the row joins the caller's transaction and the caller
    commits; otherwise it is committed in a session of its own.
    """
    try:
        row = build_log(activity_type, description, user_id)
        if session is not None:
            session.add(row)
            return True
        with database.get_session_factory()() as own:
            own.add(row)
            own.commit()
        return True
    except Exception as exc:
        logger.warning("System log '%s' not written: %s", activity_type, exc)
        return False
