from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now

SINGLETON_ID = 1


class SystemSettings(Base):
    """One row of computer-wide settings the admin edits (Phase 8).

    Every value is optional: NULL means "use server/.env", so Reset simply
    clears the columns. Order for a user: their own row → these defaults → .env.
    """

    __tablename__ = "system_settings"
    __table_args__ = (
        CheckConstraint("setting_id = 1", name="ck_system_settings_singleton"),
        CheckConstraint("dwell_ms IS NULL OR dwell_ms BETWEEN 400 AND 1500",
                        name="ck_system_settings_dwell_ms"),
        CheckConstraint("voice_volume IS NULL OR voice_volume BETWEEN 0 AND 100",
                        name="ck_system_settings_voice_volume"),
    )

    setting_id: Mapped[int] = mapped_column(primary_key=True, default=SINGLETON_ID)
    app_name: Mapped[str | None] = mapped_column(String(60))
    dwell_enabled: Mapped[bool | None] = mapped_column()
    dwell_ms: Mapped[int | None] = mapped_column(Integer)
    cursor_smoothing: Mapped[float | None] = mapped_column(Float)
    blink_to_click: Mapped[bool | None] = mapped_column()
    blink_sensitivity: Mapped[float | None] = mapped_column(Float)
    edge_scroll_enabled: Mapped[bool | None] = mapped_column()
    voice_volume: Mapped[int | None] = mapped_column(Integer)
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                 onupdate=utc_now)
