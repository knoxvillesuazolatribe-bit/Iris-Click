from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now

ROLE_ASSISTIVE_USER = "assistive_user"
ROLE_ADMIN = "admin"
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"


class User(Base):
    """Assistive users (sign in by picking their name tile) and admins (email + password).

    Not in the manuscript's ERD; every other table links to it (team decision D6).
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("role IN ('assistive_user', 'admin')", name="ck_users_role"),
        CheckConstraint("status IN ('active', 'inactive')", name="ck_users_status"),
        CheckConstraint("role <> 'admin' OR (email IS NOT NULL AND password_hash IS NOT NULL)",
                        name="ck_users_admin_login"),
    )

    user_id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=STATUS_ACTIVE,
                                        server_default=STATUS_ACTIVE)
    # Sent with an SOS alert as the user's location (team decision D8).
    address: Mapped[str | None] = mapped_column(String(255))
    barangay: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                 server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                 onupdate=utc_now, server_default=func.now())
