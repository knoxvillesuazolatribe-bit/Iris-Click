"""Accounts on this computer (file 07): /api/signin/mode and /api/accounts/*.

GET  /signin/mode             which sign-in the website should show (always answers)
GET  /accounts/tiles          the accounts added to this computer
GET  /accounts/this-computer  shared or not, and the idle sign-out time
GET  /accounts/can-sign-up    may this computer still make a new account today
POST /accounts/username-check free / taken (+ suggestions) / not allowed
POST /accounts/signup         consent + username + mobile + PIN -> account, signed in
POST /accounts/signin         a tile, or username + PIN -> signed in, added to this computer
POST /accounts/remove         forget an account on this computer
POST /accounts/signout        sign out; this computer asks for the PIN next time
POST /accounts/setup-code     PDAO's 8-digit setup code -> a short setup ticket
PUT  /accounts/me/address     the signed-in person adds their own address for Emergency SOS
POST /accounts/setup-complete the ticket + new PIN (+ username and mobile for a first account)
POST /accounts/mobile/send     text a code to verify the mobile number (sign-up, setup code)
POST /accounts/mobile/verify   the code -> a short ticket saying the number is verified
POST /accounts/mobile/confirm  (signed in) mark the account's number verified with that ticket
POST /accounts/forgot-pin/send      text a reset code to the account's verified number
POST /accounts/forgot-pin/verify    the code -> a short reset ticket
POST /accounts/forgot-pin/complete  the ticket + new PIN -> signed in, other sessions ended

Every /accounts call carries the computer ID from IrisClick Desktop in the
X-IrisClick-Device header, and answers 403 while ASSISTIVE_SIGNIN_MODE is "legacy".
Signing in sets the same irisclick_session cookie as picking a name tile does today.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.accounts import devices, mode, service, setup_codes, sms, sms_codes, usernames
from app.accounts.schemas import (AccountSessionRead, AddressRead, AddressRequest, CodeSentRead,
                                  ForgotCompleteRequest, ForgotSendRequest, ForgotVerifyRequest, MobileCodeRequest,
                                  MobileRequest, MobileTicketRequest, RemoveRequest, SetupCodeRead, TicketRead,
                                  SetupCodeRequest, SetupCompleteRequest, SigninModeRead, SigninRequest,
                                  SignupRequest, ThisComputerRead, TileRead, TilesRead, UsernameCheckRead,
                                  UsernameCheckRequest)
from app.accounts.service import AccountError, SignedInAccount
from app.api.deps import (DatabaseSafeRoute, clear_session_cookie, current_sign_in, get_db,
                          require_assistive, set_session_cookie)
from app.config import get_settings
from app.models.account_models import Device
from app.models.user import User
from app.services import active_user, session_service, sos_service
from app.services.session_service import SignedIn
from app.services.system_log_service import log_activity

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
    if result.remembered:
        set_session_cookie(response, token, result.user.role)
    else:
        # Without "Remember me" the sign-in ends when the browser (or IrisClick) closes: no expiry date,
        # so the next person must pick their tile and enter the PIN.
        response.set_cookie(session_service.COOKIE_NAME, token, path=session_service.COOKIE_PATH,
                            httponly=True, samesite="lax", secure=False)
    return response


@mode_router.get("/mode", response_model=SigninModeRead)
def signin_mode() -> SigninModeRead:
    return SigninModeRead(mode=mode.signin_mode(), sms_enabled=sms.configured())


# A person never calibrated has no accuracy: the field is left out rather than sent as null.
@router.get("/tiles", response_model=TilesRead, response_model_exclude_none=True)
def tiles(device: Device | None = Depends(known_device), db: Session = Depends(get_db)) -> TilesRead:
    found = service.list_tiles(db, device)
    return TilesRead(is_shared=bool(device and device.is_shared),
                     accounts=[TileRead(user_id=t.user_id, username=t.username, needs_pin=t.needs_pin,
                                       accuracy=t.accuracy) for t in found])


@router.get("/can-sign-up")
def can_sign_up(device: Device | None = Depends(known_device), db: Session = Depends(get_db)) -> dict:
    """Asked before "I'm new" calibrates, so nobody does the whole calibration only to be refused."""
    if service.new_account_allowed(db, device):
        return {"allowed": True}
    return {"allowed": False, "detail": service.MESSAGES["signup_limit"]}


@router.get("/this-computer", response_model=ThisComputerRead)
def this_computer(device: Device | None = Depends(known_device)) -> ThisComputerRead:
    return ThisComputerRead(is_shared=bool(device and device.is_shared),
                            idle_minutes=get_settings().shared_idle_minutes)


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
        active_user.clear_if(signed_in.user.user_id)  # as the legacy sign-out does
    session_service.revoke(db, request.cookies.get(session_service.COOKIE_NAME))
    db.commit()
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


def _setup_refusal(exc: setup_codes.SetupCodeError) -> JSONResponse:
    return JSONResponse({"detail": exc.message, "code": exc.code, **exc.extra}, status_code=exc.status_code)


@router.post("/setup-code", response_model=SetupCodeRead)
def setup_code(body: SetupCodeRequest, request: Request, device: Device | None = Depends(this_device),
               db: Session = Depends(get_db)):
    try:
        found = setup_codes.redeem(db, device, body.code, address=visitor_address(request))
    except setup_codes.SetupCodeError as exc:
        return _setup_refusal(exc)
    return SetupCodeRead(ticket=found.ticket, full_name=found.full_name, username=found.username)


@router.post("/setup-complete", response_model=AccountSessionRead)
def setup_complete(body: SetupCompleteRequest, request: Request, device: Device | None = Depends(this_device),
                   db: Session = Depends(get_db)):
    try:
        result = setup_codes.complete(db, device, ticket=body.ticket, pin=body.pin, pin_confirm=body.pin_confirm,
                                      consent=body.consent, username=body.username,
                                      mobile_number=body.mobile_number)
    except setup_codes.SetupCodeError as exc:
        return _setup_refusal(exc)
    except AccountError as exc:
        return _refusal(exc)
    return _signed_in(result, request, db)


@router.put("/me/address", response_model=AddressRead)
def my_address(body: AddressRequest, user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    """Sent with an SOS alert as the location (D8). The log never holds the address itself."""
    address, barangay = " ".join(body.address.split()), " ".join(body.barangay.split())
    if not address:
        raise HTTPException(status_code=422, detail="Type your address first.")
    row = db.get(User, user.user_id)
    row.address, row.barangay = address, barangay or None
    log_activity("address_updated", f"{row.full_name} updated their address for Emergency SOS", row.user_id,
                 session=db)
    db.commit()
    return AddressRead(location_text=sos_service.location_text(row))


# ---------- SMS: verify the mobile number, Forgot PIN (Phase 5) ----------

def _sms_refusal(exc: sms_codes.SmsCodeError) -> JSONResponse:
    return JSONResponse({"detail": exc.message, "code": exc.code, **exc.extra}, status_code=exc.status_code)


@router.post("/mobile/send", response_model=CodeSentRead)
def mobile_send(body: MobileRequest, device: Device | None = Depends(this_device), db: Session = Depends(get_db)):
    try:
        sent = sms_codes.send_verify(db, device, body.mobile_number)
    except sms_codes.SmsCodeError as exc:
        return _sms_refusal(exc)
    return CodeSentRead(to=sent.to, resend_after=sent.resend_after)


@router.post("/mobile/verify", response_model=TicketRead)
def mobile_verify(body: MobileCodeRequest, db: Session = Depends(get_db)):
    try:
        return TicketRead(ticket=sms_codes.verify_mobile(db, body.mobile_number, body.code))
    except sms_codes.SmsCodeError as exc:
        return _sms_refusal(exc)


@router.post("/mobile/confirm", status_code=204)
def mobile_confirm(body: MobileTicketRequest, user: User = Depends(require_assistive),
                   db: Session = Depends(get_db)) -> Response:
    try:
        confirmed = sms_codes.confirm_mobile(db, user.user_id, body.mobile_ticket)
    except sms_codes.SmsCodeError as exc:
        return _sms_refusal(exc)
    if not confirmed:
        raise HTTPException(status_code=409, detail="That code was for another number.")
    return Response(status_code=204)


@router.post("/forgot-pin/send", response_model=CodeSentRead)
def forgot_send(body: ForgotSendRequest, device: Device | None = Depends(known_device),
                db: Session = Depends(get_db)):
    try:
        sent = sms_codes.forgot_send(db, device, body.user_id)
    except sms_codes.SmsCodeError as exc:
        return _sms_refusal(exc)
    return CodeSentRead(to=sent.to, resend_after=sent.resend_after)


@router.post("/forgot-pin/verify", response_model=TicketRead)
def forgot_verify(body: ForgotVerifyRequest, device: Device | None = Depends(known_device),
                  db: Session = Depends(get_db)):
    try:
        return TicketRead(ticket=sms_codes.forgot_verify(db, device, body.user_id, body.code))
    except sms_codes.SmsCodeError as exc:
        return _sms_refusal(exc)


@router.post("/forgot-pin/complete", response_model=AccountSessionRead)
def forgot_complete(body: ForgotCompleteRequest, request: Request, device: Device | None = Depends(known_device),
                    db: Session = Depends(get_db)):
    try:
        account = sms_codes.forgot_complete(db, device, body.ticket, body.pin, body.pin_confirm)
        result = service.sign_in(db, device, user_id=account.user_id, pin=body.pin, remember=body.remember,
                                 address=visitor_address(request))
    except sms_codes.SmsCodeError as exc:
        return _sms_refusal(exc)
    except AccountError as exc:
        return _refusal(exc)
    return _signed_in(result, request, db)
