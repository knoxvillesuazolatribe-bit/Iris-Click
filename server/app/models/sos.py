from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now

SOS_PENDING = "pending"
SOS_SENT = "sent"
SOS_FAILED = "failed"
SOS_CANCELLED = "cancelled"


class SosContact(Base):
    """SOS_Contacts (manuscript Table 7), owned by one assistive user."""

    __tablename__ = "sos_contacts"
    __table_args__ = (
        CheckConstraint("contact_number IS NOT NULL OR email_address IS NOT NULL",
                        name="ck_sos_contacts_reachable"),
    )

    contact_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"),
                                         index=True)
    contact_name: Mapped[str] = mapped_column(String(100))
    contact_number: Mapped[str | None] = mapped_column(String(30))
    email_address: Mapped[str | None] = mapped_column(String(255))
    relationship: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SosHistory(Base):
    """SOS_History (manuscript Table "5"): one row per contact per SOS activation.

    activation_id groups the rows of one SOS press; channel, recipient and
    error_detail give the per-contact delivery status of Screen 17.
    """

    __tablename__ = "sos_history"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'sent', 'failed', 'cancelled')",
                        name="ck_sos_history_status"),
    )

    sos_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"),
                                         index=True)
    # Kept (as NULL) when the contact is later deleted; recipient still says who.
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("sos_contacts.contact_id", ondelete="SET NULL"), index=True)
    activation_id: Mapped[str] = mapped_column(String(36), index=True)
    channel: Mapped[str | None] = mapped_column(String(20))
    recipient: Mapped[str | None] = mapped_column(String(255))
    message_sent: Mapped[str] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    error_detail: Mapped[str | None] = mapped_column(Text)
    date_sent: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                index=True)
