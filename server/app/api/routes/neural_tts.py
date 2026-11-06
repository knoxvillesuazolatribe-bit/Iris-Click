"""Clearer text to speech for the signed-in assistive user.

GET/PUT /me/voice-settings, POST /me/voice-settings/reset: voice, speed, pitch.
POST /tts/speak: neural audio (JSON: base64 MP3 + word timings + source).
POST /tts/warm: pre-generates phrases (e.g. Quick Phrases) in the background.
The older POST /tts (Filipino internet voice) is unchanged and stays a fallback.
"""

import base64
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_assistive
from app.models.user import User
from app.services import neural_tts_service as tts
from app.services import voice_service
from app.services.neural_tts_service import NeuralTtsError

router = APIRouter(tags=["speech"], route_class=DatabaseSafeRoute)

Language = Literal["en", "fil"]


class VoiceRead(BaseModel):
    id: str
    name: str
    gender: str
    accent: str


class VoiceSettingsRead(BaseModel):
    voice_en: str
    voice_fil: str
    rate: int
    pitch: int
    volume: int  # the existing Voice volume setting (changed on the settings page as before)
    defaults: dict[str, int | str]
    voices: dict[str, list[VoiceRead]]
    rate_range: tuple[int, int]
    pitch_range: tuple[int, int]


class VoiceSettingsWrite(BaseModel):
    voice_en: str | None = Field(None, max_length=60)
    voice_fil: str | None = Field(None, max_length=60)
    rate: int | None = None
    pitch: int | None = None


class SpeakRequest(BaseModel):
    text: str = Field(max_length=4000)
    language: Language = "en"
    voice: str | None = Field(None, max_length=60)   # preview of an unsaved choice
    rate: int | None = None
    pitch: int | None = None


class SpeakRead(BaseModel):
    audio: str          # base64 MP3
    mime: str = "audio/mpeg"
    boundaries: list[dict]
    source: Literal["neural", "cache"]
    voice: str
    text: str           # what was read aloud, after clean-up


class WarmRequest(BaseModel):
    texts: list[str] = Field(max_length=tts.MAX_WARM)
    language: Language = "en"


def fail(exc: NeuralTtsError):
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def settings_read(db: Session, user: User) -> VoiceSettingsRead:
    s = tts.get_settings(db, user)
    return VoiceSettingsRead(
        voice_en=s.voice_en, voice_fil=s.voice_fil, rate=s.rate, pitch=s.pitch,
        volume=voice_service.voice_volume(db, user),
        defaults={"voice_en": tts.DEFAULT_VOICE["en"], "voice_fil": tts.DEFAULT_VOICE["fil"],
                  "rate": tts.DEFAULT_RATE, "pitch": tts.DEFAULT_PITCH},
        voices={lang: [VoiceRead(**v.__dict__) for v in vs] for lang, vs in tts.VOICES.items()},
        rate_range=tts.RATE_RANGE, pitch_range=tts.PITCH_RANGE)


def speakable(db: Session, text: str) -> str:
    """Word filter first: masked words become "beep" or are left out; never spoken."""
    try:
        from app.services.word_filter_service import check
    except Exception:  # noqa: BLE001
        return text
    return check(db, text).speak_text


def _resolve(db: Session, user: User, language: str, voice: str | None, rate: int | None,
             pitch: int | None) -> tuple[str, int, int]:
    saved = tts.get_settings(db, user)
    chosen = voice or (saved.voice_fil if language == "fil" else saved.voice_en)
    return chosen, saved.rate if rate is None else rate, saved.pitch if pitch is None else pitch


@router.get("/me/voice-settings", response_model=VoiceSettingsRead)
def my_settings(user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    return settings_read(db, user)


@router.put("/me/voice-settings", response_model=VoiceSettingsRead)
def save_my_settings(body: VoiceSettingsWrite, user: User = Depends(require_assistive),
                     db: Session = Depends(get_db)):
    try:
        tts.save_settings(db, user, body.model_dump())
    except NeuralTtsError as exc:
        fail(exc)
    return settings_read(db, user)


@router.post("/me/voice-settings/reset", response_model=VoiceSettingsRead)
def reset_my_settings(user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    tts.reset_settings(db, user)
    return settings_read(db, user)


@router.post("/tts/speak", response_model=SpeakRead)
def speak(body: SpeakRequest, user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    text = speakable(db, body.text)
    try:
        voice, rate, pitch = _resolve(db, user, body.language, body.voice, body.rate, body.pitch)
        speech = tts.speak(text, body.language, voice, rate, pitch)
    except NeuralTtsError as exc:
        fail(exc)
    return SpeakRead(audio=base64.b64encode(speech.audio).decode("ascii"), boundaries=speech.boundaries,
                     source=speech.source, voice=speech.voice, text=speech.text)


@router.post("/tts/warm", status_code=202)
def warm(body: WarmRequest, user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    voice, rate, pitch = _resolve(db, user, body.language, None, None, None)
    texts = [speakable(db, t) for t in body.texts if t.strip()]
    started = tts.warm_in_background(texts, body.language, voice, rate, pitch)
    return {"started": started, "count": len(texts)}
