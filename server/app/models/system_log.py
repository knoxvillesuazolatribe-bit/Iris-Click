from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now


class SystemLog(Base):
    """System_Logs (manuscript Table 10): one row per user action that matters."""

    __tablename__ = "system_logs"

    log_id: Mapped[int] = mapped_column(primary_key=True)
    # Kept (as NULL) when the user is deleted, so the audit trail survives.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"), index=True)
    activity_type: Mapped[str] = mapped_column(String(100), index=True)
    activity_description: Mapped[str | None] = mapped_column(Text)
    log_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                               index=True)
