"""English/Filipino speech for the signed-in assistive user (extension).

GET/PUT /me/language: the user's speech language (saved per user).
POST /tts: Filipino audio when the browser has no Filipino voice.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_assistive
from app.models.user import User
from app.services import speech_language_service, tts_service
from app.services.speech_language_service import LanguageError
from app.services.tts_service import TtsError

router = APIRouter(tags=["speech"], route_class=DatabaseSafeRoute)

Language = Literal["en", "fil"]


class LanguageRead(BaseModel):
    language: Language


class LanguageWrite(BaseModel):
    language: Language


class TtsRequest(BaseModel):
    text: str = Field(max_length=2000)
    language: Literal["fil"] = "fil"


@router.get("/me/language", response_model=LanguageRead)
def my_language(user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    return LanguageRead(language=speech_language_service.get_language(db, user))


@router.put("/me/language", response_model=LanguageRead)
def set_my_language(body: LanguageWrite, user: User = Depends(require_assistive),
                    db: Session = Depends(get_db)):
    try:
        return LanguageRead(language=speech_language_service.set_language(db, user, body.language))
    except LanguageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def _speakable(db: Session, text: str) -> str:
    """The word filter again, in case the page skipped it; unchanged if unavailable."""
    try:
        from app.services.word_filter_service import check
        return check(db, text).speak_text
    except Exception:  # noqa: BLE001
        return text


@router.post("/tts", responses={200: {"content": {"audio/mpeg": {}}}})
def tts(body: TtsRequest, _user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    try:
        audio = tts_service.synthesize(_speakable(db, body.text), body.language)
    except TtsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
