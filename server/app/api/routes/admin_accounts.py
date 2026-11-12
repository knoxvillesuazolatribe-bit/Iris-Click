"""Admin side of accounts on this computer (build step 14). Admin only; device_accounts mode only.

GET  /admin/accounts                              Users table columns: username, masked mobile, computers
GET  /admin/accounts/{user_id}                    the user page "Sign-in" card
POST /admin/accounts/{user_id}/reset-pin          an 8-digit setup code, shown once, valid 24 hours
POST /admin/accounts/{user_id}/unlock             clear wrong PIN tries on every computer
POST /admin/accounts/{user_id}/sign-out-everywhere end every session and every "Remember me"
PUT  /admin/accounts/this-computer                Shared computer on or off for the PC the admin is on

Admins never see or set a PIN. Answers 403 while ASSISTIVE_SIGNIN_MODE is "legacy".
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.accounts import admin, devices, setup_codes
from app.api.deps import DatabaseSafeRoute, get_db, require_admin
from app.api.routes.accounts import device_accounts_only
from app.models.user import User

router = APIRouter(prefix="/admin/accounts", tags=["admin"], route_class=DatabaseSafeRoute,
                   dependencies=[Depends(device_accounts_only)])

NOT_FOUND = "That person has no account on a computer yet."
NO_COMPUTER = "Open IrisClick Desktop on this computer, then try again."


class AccountRowRead(BaseModel):
    user_id: int
    username: str
    mobile: str
    mobile_verified: bool
    computers: int


class AccountDetailRead(AccountRowRead):
    lock: str
    must_reset_pin: bool
    shared_computers: int


class SetupCodeMade(BaseModel):
    code: str           # "1234 5678": shown to the admin once, never stored or logged
    expires_at: str


class SharedRequest(BaseModel):
    shared: bool


class SharedRead(BaseModel):
    shared: bool


@router.get("", response_model=list[AccountRowRead])
def list_accounts(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return [AccountRowRead(**row.__dict__) for row in admin.list_accounts(db)]


@router.put("/this-computer", response_model=SharedRead)
def set_this_computer(body: SharedRequest, request: Request, db: Session = Depends(get_db),
                      who: User = Depends(require_admin)):
    device = devices.remember_device(db, request.headers.get(devices.DEVICE_HEADER))
    if device is None:
        raise HTTPException(status_code=400, detail=NO_COMPUTER)
    return SharedRead(shared=admin.set_shared(db, who, device, body.shared).is_shared)


@router.get("/{user_id}", response_model=AccountDetailRead)
def account(user_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    found = admin.account_detail(db, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return AccountDetailRead(**found.__dict__)


@router.post("/{user_id}/reset-pin", response_model=SetupCodeMade)
def reset_pin(user_id: int, response: Response, db: Session = Depends(get_db), who: User = Depends(require_admin)):
    try:
        made = setup_codes.create_code(db, who, user_id)
    except setup_codes.SetupCodeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    response.headers["Cache-Control"] = "no-store"  # the code must not be kept anywhere
    return SetupCodeMade(code=setup_codes.show(made.code), expires_at=made.expires_at.isoformat())


@router.post("/{user_id}/unlock", status_code=204)
def unlock(user_id: int, db: Session = Depends(get_db), who: User = Depends(require_admin)) -> Response:
    if not admin.unlock(db, who, user_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return Response(status_code=204)


@router.post("/{user_id}/sign-out-everywhere", status_code=204)
def sign_out_everywhere(user_id: int, db: Session = Depends(get_db), who: User = Depends(require_admin)) -> Response:
    if admin.sign_out_everywhere(db, who, user_id) is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return Response(status_code=204)
