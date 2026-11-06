"""Each assistive user's speech language: English or Filipino (extension)."""

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_speech_settings import LANGUAGE_EN, SPEECH_LANGUAGES, UserSpeechSettings
from app.services.system_log_service import log_activity

NAMES = {"en": "English", "fil": "Filipino"}


class LanguageError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def get_language(db: Session, user: User) -> str:
    row = db.get(UserSpeechSettings, user.user_id)
    return row.language if row is not None else LANGUAGE_EN


def set_language(db: Session, user: User, language: str, actor: User | None = None) -> str:
    if language not in SPEECH_LANGUAGES:
        raise LanguageError(422, "Choose English or Filipino.")
    row = db.get(UserSpeechSettings, user.user_id)
    if row is not None and row.language == language:
        return language
    if row is None:
        row = UserSpeechSettings(user_id=user.user_id)
        db.add(row)
    row.language = language
    row.updated_by = (actor or user).user_id
    by = f" by {actor.full_name}" if actor is not None else ""
    log_activity("speech_language_changed",
                 f"Speech language for {user.full_name} set to {NAMES[language]}{by}",
                 (actor or user).user_id, session=db)
    db.commit()
    return language
