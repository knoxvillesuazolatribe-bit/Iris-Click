"""Per-user accessibility settings (Phase 7, team decisions D3 and D7).

No row means the standard settings (admin global defaults, else server/.env). Saving
creates or updates the row; Reset to Default deletes it. The page works in
friendly units (Low/Medium/High, steps 1-5); the row and the tracking worker
use the real values.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.accessibility_settings import (
    DEFAULT_VOICE_VOLUME,
    DWELL_MS_RANGE,
    VOICE_VOLUME_RANGE,
    AccessibilitySettings,
)
from app.models.user import User
from app.services import system_settings_service
from app.services.system_log_service import log_activity

# Cursor smoothing: higher is steadier but follows a little slower.
# "medium" is today's default (0.25).
SMOOTHING_LEVELS = {"low": 0.10, "medium": 0.25, "high": 0.45}
# Blink sensitivity steps 1 (less) to 5 (more): the eye-closure threshold.
# Step 3 is today's default (0.18). A higher threshold counts a smaller wink.
BLINK_LEVELS = (0.14, 0.16, 0.18, 0.20, 0.22)
NO_WAY_TO_CLICK = ("Turn on dwell click first. With wink-to-click and dwell click both off "
                   "there would be no way to click.")


class SettingsError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class FriendlySettings:
    dwell_enabled: bool
    dwell_ms: int
    smoothing: str
    blink_to_click: bool
    blink_sensitivity: int
    edge_scroll_enabled: bool
    voice_volume: int


def _nearest_smoothing(value: float) -> str:
    return min(SMOOTHING_LEVELS, key=lambda level: abs(SMOOTHING_LEVELS[level] - value))


def _nearest_blink_step(value: float) -> int:
    return min(range(len(BLINK_LEVELS)), key=lambda i: abs(BLINK_LEVELS[i] - value)) + 1


def _clamp(value: int, bounds: tuple[int, int]) -> int:
    return min(max(value, bounds[0]), bounds[1])


def _row(db: Session, user_id: int) -> AccessibilitySettings | None:
    return db.scalar(select(AccessibilitySettings).where(AccessibilitySettings.user_id == user_id))


def defaults(base: Settings, voice_volume: int = DEFAULT_VOICE_VOLUME) -> FriendlySettings:
    """``base`` (e.g. server/.env) in page units."""
    return FriendlySettings(
        dwell_enabled=base.dwell_click_enabled,
        dwell_ms=_clamp(base.dwell_ms, DWELL_MS_RANGE),
        smoothing=_nearest_smoothing(base.cursor_smoothing),
        blink_to_click=base.blink_click_enabled,
        blink_sensitivity=_nearest_blink_step(base.blink_threshold),
        edge_scroll_enabled=base.edge_scroll_enabled,
        voice_volume=voice_volume,
    )


def standard(db: Session, env: Settings) -> FriendlySettings:
    """What a user without their own settings gets: global defaults, else .env."""
    return defaults(system_settings_service.standard_settings(db, env),
                    system_settings_service.standard_voice(db))


def current(db: Session, user: User, base: Settings) -> tuple[FriendlySettings, bool]:
    """The user's settings in page units, and whether they are the defaults."""
    row = _row(db, user.user_id)
    if row is None:
        return standard(db, base), True
    return FriendlySettings(
        dwell_enabled=row.dwell_enabled, dwell_ms=row.dwell_ms,
        smoothing=_nearest_smoothing(row.cursor_smoothing),
        blink_to_click=row.blink_to_click,
        blink_sensitivity=_nearest_blink_step(row.blink_sensitivity),
        edge_scroll_enabled=row.edge_scroll_enabled, voice_volume=row.voice_volume,
    ), False


def save(db: Session, user: User, values: FriendlySettings, saved_by: User | None = None) -> None:
    if not values.blink_to_click and not values.dwell_enabled:
        raise SettingsError(422, NO_WAY_TO_CLICK)
    row = _row(db, user.user_id) or AccessibilitySettings(user_id=user.user_id)
    row.dwell_enabled = values.dwell_enabled
    row.dwell_ms = _clamp(values.dwell_ms, DWELL_MS_RANGE)
    row.cursor_smoothing = SMOOTHING_LEVELS[values.smoothing]
    row.blink_to_click = values.blink_to_click
    row.blink_sensitivity = BLINK_LEVELS[values.blink_sensitivity - 1]
    row.edge_scroll_enabled = values.edge_scroll_enabled
    row.voice_volume = _clamp(values.voice_volume, VOICE_VOLUME_RANGE)
    db.add(row)
    actor = saved_by or user
    log_activity("settings_updated",
                 f"Accessibility settings for {user.full_name} saved by {actor.full_name}",
                 actor.user_id, session=db)
    db.commit()


def reset(db: Session, user: User, saved_by: User | None = None) -> None:
    row = _row(db, user.user_id)
    if row is not None:
        db.delete(row)
    actor = saved_by or user
    log_activity("settings_reset",
                 f"Accessibility settings for {user.full_name} reset to default by {actor.full_name}",
                 actor.user_id, session=db)
    db.commit()


def worker_overrides(db: Session, user_id: int | None, env: Settings | None = None) -> dict | None:
    """Settings fields the tracking worker should use: the user's own settings over
    the admin's global defaults; None when neither exists (use .env as is)."""
    overrides = system_settings_service.global_overrides(db)
    row = _row(db, user_id) if user_id is not None else None
    if row is not None:
        overrides.update({
            "dwell_click_enabled": row.dwell_enabled,
            "dwell_ms": _clamp(row.dwell_ms, DWELL_MS_RANGE),
            "cursor_smoothing": row.cursor_smoothing,
            "blink_click_enabled": row.blink_to_click,
            "blink_threshold": row.blink_sensitivity,
            "edge_scroll_enabled": row.edge_scroll_enabled,
        })
    if not overrides:
        return None
    wink = overrides.get("blink_click_enabled", env.blink_click_enabled if env else True)
    dwell = overrides.get("dwell_click_enabled", env.dwell_click_enabled if env else False)
    if not wink and not dwell:
        overrides["blink_click_enabled"] = True  # never leave the user unable to click
    return overrides


def effective(db: Session, user: User, base: Settings) -> Settings:
    """``base`` with this user's settings applied (what their tracking will use)."""
    overrides = worker_overrides(db, user.user_id, base)
    return base.model_copy(update=overrides) if overrides else base


# --- Global defaults (admin, Phase 8) ------------------------------------------------

def save_global(db: Session, values: FriendlySettings, admin: User) -> None:
    if not values.blink_to_click and not values.dwell_enabled:
        raise SettingsError(422, NO_WAY_TO_CLICK)
    row = system_settings_service.row_for_update(db)
    row.dwell_enabled = values.dwell_enabled
    row.dwell_ms = _clamp(values.dwell_ms, DWELL_MS_RANGE)
    row.cursor_smoothing = SMOOTHING_LEVELS[values.smoothing]
    row.blink_to_click = values.blink_to_click
    row.blink_sensitivity = BLINK_LEVELS[values.blink_sensitivity - 1]
    row.edge_scroll_enabled = values.edge_scroll_enabled
    row.voice_volume = _clamp(values.voice_volume, VOICE_VOLUME_RANGE)
    row.updated_by = admin.user_id
    log_activity("settings_defaults_updated",
                 f"Global accessibility defaults saved by {admin.full_name}",
                 admin.user_id, session=db)
    db.commit()


def reset_global(db: Session, admin: User) -> None:
    row = system_settings_service.row(db)
    if row is not None:
        for column in (*system_settings_service.WORKER_FIELDS, "voice_volume"):
            setattr(row, column, None)
        row.updated_by = admin.user_id
    log_activity("settings_defaults_reset",
                 f"Global accessibility defaults reset to the computer's standard by {admin.full_name}",
                 admin.user_id, session=db)
    db.commit()
