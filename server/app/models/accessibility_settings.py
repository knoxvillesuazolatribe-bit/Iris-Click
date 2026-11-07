from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now

# Same values as the app.config defaults (and server/.env today), so a user
# whose row was never edited behaves exactly like the current worker.
DEFAULT_DWELL_ENABLED = False
DEFAULT_DWELL_MS = 700
DEFAULT_CURSOR_SMOOTHING = 0.25
DEFAULT_BLINK_TO_CLICK = True
DEFAULT_BLINK_SENSITIVITY = 0.18
DEFAULT_VOICE_VOLUME = 100

DWELL_MS_RANGE = (400, 1500)
CURSOR_SMOOTHING_RANGE = (0.0, 1.0)
BLINK_SENSITIVITY_RANGE = (0.05, 0.40)
VOICE_VOLUME_RANGE = (0, 100)


class AccessibilitySettings(Base):
    """Accessibility_Settings (manuscript Table 6): one row per user.

    Fixes from the data dictionary: blink_sensitivity is a number (the EAR
    threshold), not a timestamp; cursor "sensitivity" is the smoothing amount.
    """

    __tablename__ = "accessibility_settings"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_accessibility_settings_user_id"),
        CheckConstraint(f"dwell_ms BETWEEN {DWELL_MS_RANGE[0]} AND {DWELL_MS_RANGE[1]}",
                        name="ck_accessibility_settings_dwell_ms"),
        CheckConstraint("cursor_smoothing BETWEEN 0 AND 1",
                        name="ck_accessibility_settings_cursor_smoothing"),
        CheckConstraint(
            f"blink_sensitivity BETWEEN {BLINK_SENSITIVITY_RANGE[0]} AND {BLINK_SENSITIVITY_RANGE[1]}",
            name="ck_accessibility_settings_blink_sensitivity"),
        CheckConstraint("voice_volume BETWEEN 0 AND 100",
                        name="ck_accessibility_settings_voice_volume"),
    )

    setting_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"))
    # The manuscript links settings to a calibration; kept, but optional.
    calibration_id: Mapped[int | None] = mapped_column(
        ForeignKey("calibration_profiles.calibration_id", ondelete="SET NULL"), index=True)
    dwell_enabled: Mapped[bool] = mapped_column(default=DEFAULT_DWELL_ENABLED,
                                                server_default=false())
    dwell_ms: Mapped[int] = mapped_column(Integer, default=DEFAULT_DWELL_MS,
                                          server_default=str(DEFAULT_DWELL_MS))
    cursor_smoothing: Mapped[float] = mapped_column(Float, default=DEFAULT_CURSOR_SMOOTHING,
                                                    server_default=str(DEFAULT_CURSOR_SMOOTHING))
    blink_to_click: Mapped[bool] = mapped_column(default=DEFAULT_BLINK_TO_CLICK,
                                                 server_default=true())
    blink_sensitivity: Mapped[float] = mapped_column(Float, default=DEFAULT_BLINK_SENSITIVITY,
                                                     server_default=str(DEFAULT_BLINK_SENSITIVITY))
    voice_volume: Mapped[int] = mapped_column(Integer, default=DEFAULT_VOICE_VOLUME,
                                              server_default=str(DEFAULT_VOICE_VOLUME))
    # Added by migration 0003 (Phase 7): per-user edge scroll on/off.
    edge_scroll_enabled: Mapped[bool] = mapped_column(default=True, server_default=true())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                 onupdate=utc_now)
