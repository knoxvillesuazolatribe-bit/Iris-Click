"""Each assistive user's speech language for Voice Communication (extension).

Kept apart from accessibility_settings on purpose: a row there means "this
user has their own accessibility settings" (it replaces the admin's global
defaults, and Reset deletes it), so saving only a language there would
change tracking settings. No row here means English.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now

LANGUAGE_EN = "en"
LANGUAGE_FIL = "fil"
SPEECH_LANGUAGES = (LANGUAGE_EN, LANGUAGE_FIL)


class UserSpeechSettings(Base):
    __tablename__ = "user_speech_settings"
    __table_args__ = (
        CheckConstraint("language IN ('en', 'fil')", name="ck_user_speech_settings_language"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    language: Mapped[str] = mapped_column(String(5), default=LANGUAGE_EN)
    # Clearer TTS (migration 0008): empty means "use the default".
    tts_voice_en: Mapped[str | None] = mapped_column(String(60))
    tts_voice_fil: Mapped[str | None] = mapped_column(String(60))
    tts_rate: Mapped[int | None] = mapped_column(Integer)   # percent, e.g. -10
    tts_pitch: Mapped[int | None] = mapped_column(Integer)  # Hz, e.g. 0
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                 onupdate=utc_now)
