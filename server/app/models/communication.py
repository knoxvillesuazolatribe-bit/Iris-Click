from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now

MODE_TEXT_TO_SPEECH = "text_to_speech"
MODE_SPEECH_TO_TEXT = "speech_to_text"


class CommunicationHistory(Base):
    """Communication_History (manuscript Table 8): messages sent from Voice Communication."""

    __tablename__ = "communication_history"
    __table_args__ = (
        CheckConstraint("mode IN ('text_to_speech', 'speech_to_text')",
                        name="ck_communication_history_mode"),
    )

    communication_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"),
                                         index=True)
    mode: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text)
    date_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                   index=True)
    # Extension (word filter): True when words were masked before saving.
    was_filtered: Mapped[bool] = mapped_column(default=False, server_default=false())
