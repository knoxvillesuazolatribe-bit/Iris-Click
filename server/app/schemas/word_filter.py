from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["en", "fil", "other"]
Kind = Literal["blocked", "allowed"]


class CheckRequest(BaseModel):
    text: str = Field(max_length=5000)


class CheckRead(BaseModel):
    masked_text: str
    was_filtered: bool
    matches_count: int
    speak_text: str


class WordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    word_id: int
    word: str
    language: str
    type: str
    is_active: bool
    created_at: datetime


class WordCreate(BaseModel):
    word: str = Field(min_length=1, max_length=200)
    language: Language = "other"
    type: Kind = "blocked"


class FilterSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    tts_mode: Literal["beep", "skip"]


class FilterSettingsWrite(BaseModel):
    enabled: bool | None = None
    tts_mode: Literal["beep", "skip"] | None = None


class ImportRequest(BaseModel):
    content: str = Field(max_length=1_000_000)


class ImportRead(BaseModel):
    added: int
    restored: int
    skipped: int
