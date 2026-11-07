from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now


class ScreenshotHistory(Base):
    """Screenshot_History (manuscript Table 9): screenshots taken by the both-eye blink."""

    __tablename__ = "screenshot_history"

    screenshot_id: Mapped[int] = mapped_column(primary_key=True)
    # None when tracking runs without a signed-in user.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    calibration_id: Mapped[int | None] = mapped_column(
        ForeignKey("calibration_profiles.calibration_id", ondelete="SET NULL"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                  index=True)
