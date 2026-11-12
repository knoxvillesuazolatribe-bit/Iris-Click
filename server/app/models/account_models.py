"""Accounts on this computer (extension: file 07, off until ASSISTIVE_SIGNIN_MODE=device_accounts).

USER_ACCOUNTS   one row per assistive user who has a username and PIN (existing
                users get none until they set one up; the migration invents nothing)
DEVICES         one row per computer; only a SHA-256 of the computer ID kept by
                IrisClick Desktop is stored
DEVICE_ACCOUNTS which accounts were added on which computer, and "Remember me"
PIN_ATTEMPTS    wrong PIN / setup-code tries, kept in the database so limits work
                on every Vercel instance
SETUP_CODES     one-time codes from the admin's Reset PIN (Argon2 hash only)

PINs and codes are stored only as Argon2 hashes; nothing here is shown in legacy mode.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now

SIGNUP_SELF = "self"
SIGNUP_ADMIN = "admin"
ATTEMPT_PIN = "pin"
ATTEMPT_SETUP_CODE = "setup_code"


class UserAccount(Base):
    __tablename__ = "user_accounts"
    __table_args__ = (UniqueConstraint("username_key", name="uq_user_accounts_username_key"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    username: Mapped[str] = mapped_column(String(20))
    username_key: Mapped[str] = mapped_column(String(20))          # lower-case, for uniqueness
    mobile_number: Mapped[str | None] = mapped_column(String(16))    # +639XXXXXXXXX
    mobile_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pin_hash: Mapped[str | None] = mapped_column(String(255))
    pin_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    must_reset_pin: Mapped[bool] = mapped_column(default=False, server_default=false())
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signup_source: Mapped[str] = mapped_column(String(10), default=SIGNUP_SELF)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("device_key_hash", name="uq_devices_device_key_hash"),)

    device_id: Mapped[int] = mapped_column(primary_key=True)
    device_key_hash: Mapped[str] = mapped_column(String(64))
    is_shared: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceAccount(Base):
    __tablename__ = "device_accounts"
    __table_args__ = (UniqueConstraint("device_id", "user_id", name="uq_device_accounts_device_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.device_id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    remembered: Mapped[bool] = mapped_column(default=False, server_default=false())
    remembered_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PinAttempt(Base):
    __tablename__ = "pin_attempts"

    attempt_id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.device_id", ondelete="CASCADE"),
                                                  index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    address_hash: Mapped[str | None] = mapped_column(String(64))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class SetupCode(Base):
    __tablename__ = "setup_codes"

    code_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
