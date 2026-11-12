"""Accounts on this computer (file 07): /api/signin/mode and /api/accounts/*.

GET  /signin/mode             which sign-in the website should show (always answers)
GET  /accounts/tiles          the accounts added to this computer
POST /accounts/username-check free / taken (+ suggestions) / not allowed
POST /accounts/signup         consent + username + mobile + PIN -> account, signed in
POST /accounts/signin         a tile, or username + PIN -> signed in, added to this computer
POST /accounts/remove         forget an account on this computer
POST /accounts/signout        sign out; this computer asks for the PIN next time

Every /accounts call carries the computer ID from IrisClick Desktop in the
X-IrisClick-Device header, and answers 403 while ASSISTIVE_SIGNIN_MODE is "legacy".
Signing in sets the same irisclick_session cookie as picking a name tile does today.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.accounts import devices, mode, service, usernames
from app.accounts.schemas import (AccountSessionRead, RemoveRequest, SigninModeRead, SigninRequest,
                                  SignupRequest, TileRead, TilesRead, UsernameCheckRead, UsernameCheckRequest)
from app.accounts.service import AccountError, SignedInAccount
from app.api.deps import (DatabaseSafeRoute, clear_session_cookie, current_sign_in, get_db,
                          set_session_cookie)
from app.models.account_models import Device
from app.services import session_service
from app.services.session_service import SignedIn

LEGACY_MODE = "Accounts on this computer are not turned on."


def device_accounts_only() -> None:
    if not mode.device_accounts_on():
        raise HTTPException(status_code=403, detail=LEGACY_MODE)


mode_router = APIRouter(prefix="/signin", tags=["accounts"])
router = APIRouter(prefix="/accounts", tags=["accounts"], route_class=DatabaseSafeRoute,
                   dependencies=[Depends(device_accounts_only)])


def visitor_address(request: Request) -> str | None:
    # Vercel sets x-real-ip / x-forwarded-for to the visitor's address (same as app/cloud/access.py).
    forwarded = (request.headers.get("x-real-ip")
                 or request.headers.get("x-forwarded-for", "").split(",")[0]).strip()
    return forwarded or (request.client.host if request.client else None)


def known_device(request: Request, db: Session = Depends(get_db)) -> Device | None:
    """This computer if the server has seen it before (looking never adds a row)."""
    return devices.find_device(db, request.headers.get(devices.DEVICE_HEADER))


def this_device(request: Request, db: Session = Depends(get_db)) -> Device | None:
    """This computer, added on first use. None when the header is missing or malformed."""
    return devices.remember_device(db, request.headers.get(devices.DEVICE_HEADER))


def _refusal(exc: AccountError) -> JSONResponse:
    return JSONResponse({"detail": exc.message, "code": exc.code, **exc.extra}, status_code=exc.status_code)


def _signed_in(result: SignedInAccount, request: Request, db: Session) -> JSONResponse:
    session_service.revoke(db, request.cookies.get(session_service.COOKIE_NAME))
    token = session_service.create_session(db, result.user)
    db.commit()
    body = AccountSessionRead(user_id=result.user.user_id, full_name=result.user.full_name, username=result.username)
    response = JSONResponse(body.model_dump())
    set_session_cookie(response, token, result.user.role)
    return response


@mode_router.get("/mode", response_model=SigninModeRead)
def signin_mode() -> SigninModeRead:
    return SigninModeRead(mode=mode.signin_mode())


@router.get("/tiles", response_model=TilesRead)
def tiles(device: Device | None = Depends(known_device), db: Session = Depends(get_db)) -> TilesRead:
    found = service.list_tiles(db, device)
    return TilesRead(is_shared=bool(device and device.is_shared),
                     accounts=[TileRead(user_id=t.user_id, username=t.username, needs_pin=t.needs_pin) for t in found])


@router.post("/username-check", response_model=UsernameCheckRead)
def username_check(body: UsernameCheckRequest, db: Session = Depends(get_db)) -> UsernameCheckRead:
    problem = usernames.check_username(db, body.username)
    if problem is None:
        return UsernameCheckRead(available=True)
    return UsernameCheckRead(available=False, problem=problem, message=service.MESSAGES[problem],
                             suggestions=usernames.suggestions(db, body.username) if problem == usernames.TAKEN else [])


@router.post("/signup", response_model=AccountSessionRead, status_code=201)
def signup(body: SignupRequest, request: Request, device: Device | None = Depends(this_device),
           db: Session = Depends(get_db)):
    try:
        result = service.sign_up(db, device, consent=body.consent, username=body.username,
                                 mobile_number=body.mobile_number, pin=body.pin, pin_confirm=body.pin_confirm,
                                 remember=body.remember)
    except AccountError as exc:
        return _refusal(exc)
    response = _signed_in(result, request, db)
    response.status_code = 201
    return response


@router.post("/signin", response_model=AccountSessionRead)
def signin(body: SigninRequest, request: Request, device: Device | None = Depends(this_device),
           db: Session = Depends(get_db)):
    if (body.user_id is None) == (body.username is None):
        raise HTTPException(status_code=422, detail="Send a tile (user_id) or a username, not both.")
    try:
        result = service.sign_in(db, device, user_id=body.user_id, username=body.username, pin=body.pin,
                                 remember=body.remember, address=visitor_address(request))
    except AccountError as exc:
        return _refusal(exc)
    return _signed_in(result, request, db)


@router.post("/remove", status_code=204)
def remove(body: RemoveRequest, request: Request, device: Device | None = Depends(known_device),
           db: Session = Depends(get_db)):
    try:
        service.remove_from_computer(db, device, user_id=body.user_id, pin=body.pin,
                                     address=visitor_address(request))
    except AccountError as exc:
        return _refusal(exc)
    return Response(status_code=204)


@router.post("/signout", status_code=204)
def signout(request: Request, device: Device | None = Depends(known_device),
            signed_in: SignedIn | None = Depends(current_sign_in), db: Session = Depends(get_db)) -> Response:
    if signed_in is not None:
        service.forget_remember_me(db, device, signed_in.user.user_id)
    session_service.revoke(db, request.cookies.get(session_service.COOKIE_NAME))
    db.commit()
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response
