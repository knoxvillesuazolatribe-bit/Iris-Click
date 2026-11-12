"""Computer lock routes (website only; app/services/approved_computers.py has the rules).

- Admin, on a person's page: list approved computers, make a one-time approval link,
  "Approve this computer", remove a computer.
- POST /api/cloud/computers/claim: the approval link, opened on the person's computer.
  It works without the access code: the one-time code protects it.
- With IRISCLICK_COMPUTER_LOCK=on, the name screen (GET /api/assistive/users) and
  "pick a name" (POST /api/assistive/select) only allow people approved on this
  computer. With it off, they answer exactly as before.
"""

import logging
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.accounts.guards import ADDED_ON_COMPUTER, USE_YOUR_PIN, legacy_only
from app.api.deps import (DatabaseSafeRoute, current_sign_in, get_db, require_admin,
                          require_signed_in)
from app.api.routes import assistive
from app.cloud import access
from app.models.user import User
from app.schemas.auth import AssistiveSelectRequest
from app.services import approved_computers as computers
from app.services.approved_computers import ComputerError
from app.services.session_service import SignedIn

logger = logging.getLogger("irisclick.cloud.computers")

COOKIE_NAME = "irisclick_computer"
COOKIE_MAX_AGE_S = 2 * 365 * 24 * 3600
CLAIM_PATH = "/cloud/computers/claim"
NOT_APPROVED_CODE = "computer_not_approved"
NOT_APPROVED = ("This computer is not approved for IrisClick yet. "
                "Ask your helper or the PDAO office for an approval link.")
NAME_NOT_APPROVED = ("Your name is not approved on this computer yet. "
                     "Ask your helper or the PDAO office for an approval link.")

admin_router = APIRouter(prefix="/admin/users/{user_id}/computers", tags=["computer lock"],
                         route_class=DatabaseSafeRoute)
claim_router = APIRouter(tags=["computer lock"], route_class=DatabaseSafeRoute)
sign_in_router = APIRouter(prefix="/assistive", tags=["computer lock"], route_class=DatabaseSafeRoute)

wrong_codes = access._WrongCodes()  # same pause as wrong access codes, counted apart


class ComputerRead(BaseModel):
    computer_id: int
    label: str
    status: str
    created_at: datetime
    approved_at: datetime | None
    last_used_at: datetime | None
    code_expires_at: datetime | None
    this_computer: bool


class ComputerList(BaseModel):
    lock_on: bool
    computers: list[ComputerRead]


class LabelRequest(BaseModel):
    label: str | None = Field(default=None, max_length=200)


class LinkRead(BaseModel):
    code: str
    path: str
    expires_at: datetime


class ClaimRequest(BaseModel):
    code: str = Field(min_length=10, max_length=200)


class ClaimRead(BaseModel):
    full_name: str


def computer_key(request: Request) -> str | None:
    return computers.usable_key(request.cookies.get(COOKIE_NAME))


def set_computer_cookie(response: Response, request: Request, key: str) -> None:
    response.set_cookie(COOKIE_NAME, key, max_age=COOKIE_MAX_AGE_S, path="/", httponly=True,
                        samesite="lax", secure=access.is_https(request))


def _fail(exc: ComputerError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def admin_when_locked(signed_in: SignedIn | None = Depends(current_sign_in)) -> None:
    """With the computer lock on (the access code can then be removed), the setup check
    needs an admin sign-in instead of the access code."""
    if computers.lock_on():
        require_admin(require_signed_in(signed_in))


# --- Admin ----------------------------------------------------------------------------------

@admin_router.get("", response_model=ComputerList)
def list_computers(user_id: int, request: Request, _admin: User = Depends(require_admin),
                   db: Session = Depends(get_db)) -> ComputerList:
    try:
        views = computers.list_for_user(db, user_id, computer_key(request))
    except ComputerError as exc:
        raise _fail(exc) from exc
    return ComputerList(lock_on=computers.lock_on(),
                        computers=[ComputerRead.model_validate(v, from_attributes=True) for v in views])


@admin_router.post("/link", response_model=LinkRead, dependencies=[Depends(legacy_only(ADDED_ON_COMPUTER))])
def make_link(user_id: int, body: LabelRequest, admin: User = Depends(require_admin),
              db: Session = Depends(get_db)) -> LinkRead:
    try:
        code, expires = computers.make_link(db, user_id, body.label, admin)
    except ComputerError as exc:
        raise _fail(exc) from exc
    db.commit()
    # The code goes after "#": browsers never send that part to a server, so it stays out of logs.
    return LinkRead(code=code, path=f"/approve#{code}", expires_at=expires)


@admin_router.post("/this", response_model=ComputerRead, dependencies=[Depends(legacy_only(ADDED_ON_COMPUTER))])
def approve_this_computer(user_id: int, body: LabelRequest, request: Request, response: Response,
                          admin: User = Depends(require_admin),
                          db: Session = Depends(get_db)) -> ComputerRead:
    try:
        row, key = computers.approve_here(db, user_id, body.label, admin, computer_key(request))
    except ComputerError as exc:
        raise _fail(exc) from exc
    db.commit()
    set_computer_cookie(response, request, key)
    view = next(v for v in computers.list_for_user(db, user_id, key) if v.computer_id == row.computer_id)
    return ComputerRead.model_validate(view, from_attributes=True)


@admin_router.delete("/{computer_id}", status_code=204)
def remove_computer(user_id: int, computer_id: int, admin: User = Depends(require_admin),
                    db: Session = Depends(get_db)) -> Response:
    try:
        computers.remove(db, user_id, computer_id, admin)
    except ComputerError as exc:
        raise _fail(exc) from exc
    db.commit()
    return Response(status_code=204)


# --- The approval link ----------------------------------------------------------------------

@claim_router.post(CLAIM_PATH, response_model=ClaimRead)
def claim(body: ClaimRequest, request: Request, response: Response,
          db: Session = Depends(get_db)) -> ClaimRead:
    address = access.client_address(request)
    now = time.monotonic()
    if wrong_codes.blocked(address, now):
        raise HTTPException(status_code=429, detail="Too many tries. Please wait 15 minutes and try again.")
    try:
        user, key = computers.claim(db, body.code, computer_key(request))
    except ComputerError as exc:
        if exc.status_code == 401:
            wrong_codes.add(address, now)
            logger.warning("Approval link not valid, from %s", address)
            access.sleep(access.WRONG_CODE_DELAY_S)
        raise _fail(exc) from exc
    db.commit()
    set_computer_cookie(response, request, key)
    return ClaimRead(full_name=user.full_name)


# --- Name screen with the lock on -----------------------------------------------------------

def _not_approved(message: str) -> JSONResponse:
    return JSONResponse({"detail": message, "code": NOT_APPROVED_CODE}, status_code=403)


@sign_in_router.get("/users", dependencies=[Depends(legacy_only(USE_YOUR_PIN))])
def list_users(request: Request, response: Response, db: Session = Depends(get_db)):
    if not computers.lock_on():
        return assistive.list_users(db)
    key = computer_key(request)
    allowed = computers.approved_user_ids(db, key)
    if not allowed:
        return _not_approved(NOT_APPROVED)
    set_computer_cookie(response, request, key)  # two more years from today
    tiles = assistive.list_users(db)
    return [tile for tile in tiles if tile.user_id in allowed]


@sign_in_router.post("/select", dependencies=[Depends(legacy_only(USE_YOUR_PIN))])
def select_user(body: AssistiveSelectRequest, request: Request, response: Response,
                db: Session = Depends(get_db)):
    if not computers.lock_on():
        return assistive.select_user(body, request, response, db)
    key = computer_key(request)
    if body.user_id not in computers.approved_user_ids(db, key):
        return _not_approved(NAME_NOT_APPROVED)
    signed_in = assistive.select_user(body, request, response, db)
    computers.mark_used(db, key, body.user_id)
    db.commit()
    return signed_in
