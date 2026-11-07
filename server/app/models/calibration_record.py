from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now

STATUS_SUCCESSFUL = "Successful"
STATUS_FAILED = "Failed"


class CalibrationRecord(Base):
    """Calibration_Profiles (manuscript Table 5): one row per calibration attempt.

    The JSON profile in storage/ is still what the tracker loads; this row is
    its database copy (team decision D5). Failed attempts have no file.
    """

    __tablename__ = "calibration_profiles"
    __table_args__ = (
        UniqueConstraint("profile_file_id", name="uq_calibration_profiles_profile_file_id"),
        CheckConstraint("status IN ('Successful', 'Failed')", name="ck_calibration_profiles_status"),
    )

    calibration_id: Mapped[int] = mapped_column(primary_key=True)
    # None until the sign-in flow (Phase 2) says who is calibrating.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    # Id of the storage/calibration_profiles/<id>.json file; None for failures.
    profile_file_id: Mapped[str | None] = mapped_column(String(64))
    profile_name: Mapped[str] = mapped_column(String(60))
    # round((1 - error_fraction) * 100, 2); the manuscript's "accuracy percentage".
    accuracy_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # Original per-dot error as a fraction of the screen (lower is better).
    error_fraction: Mapped[float | None] = mapped_column(Float)
    low_accuracy: Mapped[bool | None]
    feature_source: Mapped[str | None] = mapped_column(String(50))
    camera_index: Mapped[int | None] = mapped_column(Integer)
    sample_count: Mapped[int | None] = mapped_column(Integer)
    # The full saved profile (fitted model, screen, posture, candidates).
    calibration_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    calibration_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                       index=True)
