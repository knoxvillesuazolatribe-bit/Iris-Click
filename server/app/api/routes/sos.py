"""Emergency SOS for the signed-in assistive user."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_assistive
from app.models.user import User
from app.schemas.sos import (
    SosActivateRequest,
    SosActivationRead,
    SosContactRead,
    SosContactWrite,
    SosOverviewRead,
)
from app.services import sos_service
from app.services.sos_service import SosError

router = APIRouter(prefix="/me/sos", tags=["sos"], route_class=DatabaseSafeRoute)


def _fail(exc: SosError):
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("", response_model=SosOverviewRead)
def overview(user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    return SosOverviewRead.model_validate(sos_service.overview(db, user), from_attributes=True)


@router.get("/contacts", response_model=list[SosContactRead])
def list_contacts(user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    return [SosContactRead.model_validate(c) for c in sos_service.list_contacts(db, user)]


@router.post("/contacts", response_model=SosContactRead, status_code=201)
def add_contact(body: SosContactWrite, user: User = Depends(require_assistive),
                db: Session = Depends(get_db)):
    try:
        return SosContactRead.model_validate(sos_service.add_contact(db, user, body.model_dump()))
    except SosError as exc:
        _fail(exc)


@router.put("/contacts/{contact_id}", response_model=SosContactRead)
def update_contact(contact_id: int, body: SosContactWrite,
                   user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    try:
        return SosContactRead.model_validate(
            sos_service.update_contact(db, user, contact_id, body.model_dump()))
    except SosError as exc:
        _fail(exc)


@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(contact_id: int, user: User = Depends(require_assistive),
                   db: Session = Depends(get_db)):
    try:
        sos_service.delete_contact(db, user, contact_id)
    except SosError as exc:
        _fail(exc)
    return Response(status_code=204)


@router.post("/activate", response_model=SosActivationRead)
def activate(body: SosActivateRequest, user: User = Depends(require_assistive),
             db: Session = Depends(get_db)):
    """Starts sending to every contact; the page then polls the activation."""
    try:
        activation_id = sos_service.activate(db, user, str(body.activation_id))
        return SosActivationRead.model_validate(
            sos_service.activation_view(db, user, activation_id), from_attributes=True)
    except SosError as exc:
        _fail(exc)


@router.get("/activations/{activation_id}", response_model=SosActivationRead)
def activation(activation_id: str, user: User = Depends(require_assistive),
               db: Session = Depends(get_db)):
    try:
        return SosActivationRead.model_validate(
            sos_service.activation_view(db, user, activation_id), from_attributes=True)
    except SosError as exc:
        _fail(exc)


@router.post("/cancel", status_code=204)
def cancel(user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    sos_service.cancel(db, user)
    return Response(status_code=204)
