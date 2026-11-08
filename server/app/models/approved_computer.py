"""A computer approved for one assistive user on the website (extension: computer lock).

The website has no password for assistive users: they pick their name. With
the computer lock on, a name only shows on computers a helper approved once,
with an approval link from the admin page or "Approve this computer".

A row starts as a waiting approval link (code_hash, code_expires_at). Opening
the link on the person's computer fills key_hash: the browser keeps the key
in a cookie. Only SHA-256 hashes are stored, never the code or the key.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now


class ApprovedComputer(Base):
    __tablename__ = "approved_computers"
    __table_args__ = (UniqueConstraint("code_hash", name="uq_approved_computers_code_hash"),)

    computer_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(80))
    code_hash: Mapped[str | None] = mapped_column(String(64))
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    key_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
