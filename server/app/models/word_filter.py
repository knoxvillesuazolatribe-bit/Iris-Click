"""Word filter for Voice Communication (extension of Objective 2.5).

``filtered_words`` holds blocked words (masked) and allowed words (never
masked, even if they look like a blocked one). Removing a word is a soft
delete so it can be restored. ``word_filter_settings`` is one row: on/off and
what text-to-speech does with a masked word.
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.timestamps import utc_now

TYPE_BLOCKED = "blocked"
TYPE_ALLOWED = "allowed"
LANGUAGES = ("en", "fil", "other")
TTS_BEEP = "beep"
TTS_SKIP = "skip"
SETTINGS_ID = 1


class FilteredWord(Base):
    __tablename__ = "filtered_words"
    __table_args__ = (
        CheckConstraint("language IN ('en', 'fil', 'other')", name="ck_filtered_words_language"),
        CheckConstraint("type IN ('blocked', 'allowed')", name="ck_filtered_words_type"),
    )

    word_id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(String(100))
    normalized_word: Mapped[str] = mapped_column(String(100), unique=True)
    language: Mapped[str] = mapped_column(String(10), default="other")
    type: Mapped[str] = mapped_column(String(10), default=TYPE_BLOCKED)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                 onupdate=utc_now)


class WordFilterSettings(Base):
    __tablename__ = "word_filter_settings"
    __table_args__ = (
        CheckConstraint("setting_id = 1", name="ck_word_filter_settings_singleton"),
        CheckConstraint("tts_mode IN ('beep', 'skip')", name="ck_word_filter_settings_tts_mode"),
    )

    setting_id: Mapped[int] = mapped_column(primary_key=True, default=SETTINGS_ID)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    tts_mode: Mapped[str] = mapped_column(String(10), default=TTS_BEEP)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                 onupdate=utc_now)
