"""Per-user Apps tiles on the Home Suite (extension of Scope p. 4).

The six fixed apps of Phase 9 are seeded as "builtin" rows. Hiding a builtin
keeps its row so it can be added back; installed apps and websites the user
adds are real rows that can be deleted.
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now

KIND_BUILTIN = "builtin"
KIND_INSTALLED = "installed_app"
KIND_WEBSITE = "website"


class UserAppShortcut(Base):
    __tablename__ = "user_app_shortcuts"
    __table_args__ = (
        CheckConstraint("type IN ('builtin', 'installed_app', 'website')", name="ck_user_app_shortcuts_type"),
        UniqueConstraint("user_id", "builtin_key", name="uq_user_app_shortcuts_builtin"),
        UniqueConstraint("user_id", "target", name="uq_user_app_shortcuts_target"),
    )

    shortcut_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(60))
    type: Mapped[str] = mapped_column(String(20))
    builtin_key: Mapped[str | None] = mapped_column(String(20))
    target: Mapped[str | None] = mapped_column(String(2048))
    icon: Mapped[str] = mapped_column(String(30))
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                 onupdate=utc_now)
