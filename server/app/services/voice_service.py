"""Voice Communication: the user's speaking volume and their sent messages.

system_logs record only the kind and length of a message, never its text,
because messages can be private.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.accessibility_settings import AccessibilitySettings
from app.models.communication import MODE_TEXT_TO_SPEECH, CommunicationHistory
from app.models.user import User
from app.services import system_settings_service
from app.services.system_log_service import log_activity

RECENT_LIMIT = 10
MAX_MESSAGE_CHARS = 1000
MODE_LABELS = {MODE_TEXT_TO_SPEECH: "text-to-speech"}


class VoiceError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def voice_volume(db: Session, user: User) -> int:
    """0–100: the user's setting, else the admin's global default, else 100."""
    volume = db.scalar(select(AccessibilitySettings.voice_volume)
                       .where(AccessibilitySettings.user_id == user.user_id))
    return system_settings_service.standard_voice(db) if volume is None else volume


def recent_messages(db: Session, user: User, limit: int = RECENT_LIMIT) -> list[CommunicationHistory]:
    return list(db.scalars(
        select(CommunicationHistory)
        .where(CommunicationHistory.user_id == user.user_id)
        .order_by(CommunicationHistory.date_created.desc(),
                  CommunicationHistory.communication_id.desc())
        .limit(limit)
    ))


def _kind(mode: str) -> str:
    return MODE_LABELS.get(mode, "speech-to-text")


def save_message(db: Session, user: User, mode: str, message: str) -> CommunicationHistory:
    row = CommunicationHistory(user_id=user.user_id, mode=mode, message=message)
    db.add(row)
    db.flush()
    log_activity("communication_sent",
                 f"{user.full_name} sent a {_kind(mode)} message ({len(message)} characters)",
                 user.user_id, session=db)
    db.commit()
    db.refresh(row)
    return row


def delete_message(db: Session, user: User, communication_id: int) -> None:
    """Deletes one of the user's own messages; someone else's looks not found."""
    row = db.get(CommunicationHistory, communication_id)
    if row is None or row.user_id != user.user_id:
        raise VoiceError(404, "That message was not found. It may already be deleted.")
    mode = row.mode
    db.delete(row)
    log_activity("communication_deleted", f"{user.full_name} deleted a {_kind(mode)} message",
                 user.user_id, session=db)
    db.commit()
