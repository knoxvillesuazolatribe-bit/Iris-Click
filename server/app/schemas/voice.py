from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.services.voice_service import MAX_MESSAGE_CHARS

Mode = Literal["text_to_speech", "speech_to_text"]
Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                           max_length=MAX_MESSAGE_CHARS)]


class CommunicationCreate(BaseModel):
    mode: Mode
    message: Message
    language: Literal["en", "fil"] = "en"  # extension: bilingual speech


class CommunicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    communication_id: int
    mode: Mode
    message: str
    date_created: datetime
    language: str | None = None  # extension: bilingual speech


class VoiceRead(BaseModel):
    voice_volume: int
    messages: list[CommunicationRead]
