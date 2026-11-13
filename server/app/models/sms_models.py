"""SMS_CODES (file 07, Phase 5): 6-digit codes sent by text, Argon2 hash only.

purpose  "verify_mobile" (sign-up: is this your number?) or "reset_pin" (Forgot PIN)
The number itself is not stored: ``mobile_hash`` is an HMAC of it, enough to match the
code to the number and to count texts per number for the limits.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now

PURPOSE_VERIFY = "verify_mobile"
PURPOSE_RESET = "reset_pin"


class SmsCode(Base):
    __tablename__ = "sms_codes"

    code_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.device_id", ondelete="SET NULL"))
    mobile_hash: Mapped[str] = mapped_column(String(64), index=True)
    purpose: Mapped[str] = mapped_column(String(16))
    code_hash: Mapped[str] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
