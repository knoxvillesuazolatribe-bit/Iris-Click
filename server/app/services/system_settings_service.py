"""Computer-wide settings the admin edits (Phase 8): app name and global defaults.

Global defaults sit between server/.env and each user's own settings. A NULL
column means "use .env", so Reset clears the columns rather than storing copies.
"""

from sqlalchemy.orm import Session

from app.config import Settings
from app.models.accessibility_settings import DEFAULT_VOICE_VOLUME
from app.models.system_settings import SINGLETON_ID, SystemSettings

# system_settings column → Settings field the tracking worker reads.
WORKER_FIELDS = {
    "dwell_enabled": "dwell_click_enabled",
    "dwell_ms": "dwell_ms",
    "cursor_smoothing": "cursor_smoothing",
    "blink_to_click": "blink_click_enabled",
    "blink_sensitivity": "blink_threshold",
    "edge_scroll_enabled": "edge_scroll_enabled",
}
APP_NAME_MAX = 60


def row(db: Session) -> SystemSettings | None:
    return db.get(SystemSettings, SINGLETON_ID)


def row_for_update(db: Session) -> SystemSettings:
    existing = row(db)
    if existing is not None:
        return existing
    created = SystemSettings(setting_id=SINGLETON_ID)
    db.add(created)
    return created


def global_overrides(db: Session) -> dict:
    """Settings fields set by the admin's global defaults (empty: all from .env)."""
    current = row(db)
    if current is None:
        return {}
    return {field: getattr(current, column) for column, field in WORKER_FIELDS.items()
            if getattr(current, column) is not None}


def has_global_defaults(db: Session) -> bool:
    return bool(global_overrides(db)) or standard_voice_override(db) is not None


def standard_voice_override(db: Session) -> int | None:
    current = row(db)
    return current.voice_volume if current is not None else None


def standard_settings(db: Session, env: Settings) -> Settings:
    """.env with the admin's global defaults applied: what a user starts from."""
    overrides = global_overrides(db)
    return env.model_copy(update=overrides) if overrides else env


def standard_voice(db: Session) -> int:
    value = standard_voice_override(db)
    return DEFAULT_VOICE_VOLUME if value is None else value


def app_name(db: Session, env: Settings) -> str:
    current = row(db)
    return (current.app_name if current is not None and current.app_name else env.app_name)
