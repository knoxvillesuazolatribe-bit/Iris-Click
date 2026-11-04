"""Voice Communication for the signed-in assistive user."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_assistive
from app.models.timestamps import as_utc
from app.models.user import User
from app.schemas.voice import CommunicationCreate, CommunicationRead, VoiceRead
from app.services import voice_service
from app.services.voice_service import VoiceError

router = APIRouter(prefix="/me", tags=["voice"], route_class=DatabaseSafeRoute)


def _read(row) -> CommunicationRead:
    read = CommunicationRead.model_validate(row)
    return read.model_copy(update={"date_created": as_utc(row.date_created)})


@router.get("/voice", response_model=VoiceRead)
def voice(user: User = Depends(require_assistive), db: Session = Depends(get_db)) -> VoiceRead:
    return VoiceRead(voice_volume=voice_service.voice_volume(db, user),
                     messages=[_read(row) for row in voice_service.recent_messages(db, user)])


@router.post("/communications", response_model=CommunicationRead, status_code=201)
def send_message(body: CommunicationCreate, user: User = Depends(require_assistive),
                 db: Session = Depends(get_db)) -> CommunicationRead:
    return _read(voice_service.save_message(db, user, body.mode, body.message))


@router.delete("/communications/{communication_id}", status_code=204)
def delete_message(communication_id: int, user: User = Depends(require_assistive),
                   db: Session = Depends(get_db)) -> Response:
    try:
        voice_service.delete_message(db, user, communication_id)
    except VoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return Response(status_code=204)
