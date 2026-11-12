"""Setup codes (file 07, plan D3, build step 11): PDAO's way back in for a person.

The administrator's Reset PIN makes an 8-digit code (shown once, as ``1234 5678``),
valid for 24 hours and for one use. Only its Argon2 hash is kept. The person types it on
their computer ("I have a setup code from PDAO"):

* someone who already has an account chooses a new PIN;
* someone from before accounts existed (made by the admin, no username yet) chooses a
  username, a mobile number and a PIN; their calibrations, messages and contacts stay.

A correct code gives a short signed "setup ticket" (15 minutes) that the last screen
sends back with the new PIN, so the code itself is typed only once. Wrong codes count
against this computer and the whole site (limits.setup_code_state).
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.accounts import limits, mobiles, pins, usernames
from app.models.account_models import ATTEMPT_SETUP_CODE, SIGNUP_ADMIN, Device, SetupCode, UserAccount
from app.models.timestamps import as_utc, utc_now
from app.models.user import ROLE_ASSISTIVE_USER, STATUS_ACTIVE, User
from app.services import password_hashing
from app.services.system_log_service import log_activity

CODE_DIGITS = 8
CODE_LIFETIME = timedelta(hours=24)
TICKET_LIFETIME_S = 15 * 60


class SetupCodeError(Exception):
    def __init__(self, status_code: int, code: str, message: str, **extra):
        super().__init__(code)
        self.status_code, self.code, self.message, self.extra = status_code, code, message, extra


WRONG_CODE = "That setup code is not right, or it has expired. Check it with PDAO staff."
TICKET_EXPIRED = "This took too long. Please type your setup code again."


def is_code(text: object) -> bool:
    return isinstance(text, str) and len(text) == CODE_DIGITS and text.isascii() and text.isdigit()


def clean(text: object) -> str:
    """``1234 5678`` or ``1234-5678`` -> ``12345678``."""
    return "".join(c for c in text if c.isdigit()) if isinstance(text, str) else ""


def show(code: str) -> str:
    return f"{code[:4]} {code[4:]}"


# ---------- the administrator's side ----------

@dataclass(frozen=True)
class NewCode:
    code: str            # shown to the administrator once, never stored
    expires_at: datetime


def create_code(db: Session, admin: User, user_id: int, now: datetime | None = None) -> NewCode:
    """A fresh code for an active assistive user; earlier unused codes stop working."""
    now = now or utc_now()
    user = db.get(User, user_id)
    if user is None or user.role != ROLE_ASSISTIVE_USER or user.status != STATUS_ACTIVE:
        raise SetupCodeError(404, "not_found", "That person was not found or is inactive.")
    db.execute(update(SetupCode).where(SetupCode.user_id == user_id, SetupCode.used_at.is_(None))
               .values(used_at=now))
    code = "".join(secrets.choice("0123456789") for _ in range(CODE_DIGITS))
    db.add(SetupCode(user_id=user_id, code_hash=password_hashing.hash_password(code),
                     expires_at=now + CODE_LIFETIME, created_by=admin.user_id, created_at=now))
    account = db.get(UserAccount, user_id)
    if account is not None:
        account.must_reset_pin = True  # the old PIN stops working; remembered computers still open
    log_activity("pin_reset_by_admin", f"{admin.full_name} made a setup code for {user.full_name}", user_id,
                 session=db)
    db.commit()
    return NewCode(code, now + CODE_LIFETIME)


# ---------- the setup ticket ----------

def _ticket_key() -> bytes:
    from app.services import desktop_tokens
    return hashlib.sha256(b"irisclick-setup-ticket-v1:" + desktop_tokens._key()).digest()  # noqa: SLF001


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_ticket(code_id: int, user_id: int, now: float | None = None) -> str:
    expires = int(now if now is not None else time.time()) + TICKET_LIFETIME_S
    payload = _b64(json.dumps({"c": code_id, "u": user_id, "e": expires}, separators=(",", ":")).encode())
    return payload + "." + _b64(hmac.new(_ticket_key(), payload.encode(), hashlib.sha256).digest())


def read_ticket(ticket: object, now: float | None = None) -> tuple[int, int]:
    """(code_id, user_id) from a valid, unexpired ticket; raises SetupCodeError otherwise."""
    try:
        payload, signature = str(ticket).split(".", 1)
        expected = _b64(hmac.new(_ticket_key(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        code_id, user_id, expires = int(data["c"]), int(data["u"]), int(data["e"])
    except Exception as exc:  # noqa: BLE001 - any broken ticket is simply invalid
        raise SetupCodeError(401, "ticket_expired", TICKET_EXPIRED) from exc
    if (now if now is not None else time.time()) >= expires:
        raise SetupCodeError(401, "ticket_expired", TICKET_EXPIRED)
    return code_id, user_id


# ---------- the person's side ----------

@dataclass(frozen=True)
class Redeemed:
    ticket: str
    user_id: int
    full_name: str
    username: str | None   # None: no account yet, so they choose a username and mobile number


def _usable(db: Session, now: datetime) -> list[SetupCode]:
    rows = db.scalars(select(SetupCode).where(SetupCode.used_at.is_(None), SetupCode.expires_at > now)
                      .order_by(SetupCode.created_at.desc()).limit(50)).all()
    return [r for r in rows if as_utc(r.expires_at) > now]


def redeem(db: Session, device: Device | None, code: object, address: str | None = None,
           now: datetime | None = None) -> Redeemed:
    now = now or utc_now()
    if device is None:
        raise SetupCodeError(400, "device_required", "Open IrisClick Desktop on this computer, then try again.")
    state = limits.setup_code_state(db, device_id=device.device_id, now=now)
    if not state.allowed:
        raise SetupCodeError(429, "wait", "Too many wrong codes. Please wait, then try again.",
                             wait_seconds=state.wait_seconds)
    typed = clean(code)
    match = None
    if is_code(typed):
        match = next((row for row in _usable(db, now) if password_hashing.verify_password(row.code_hash, typed)), None)
    else:
        password_hashing.verify_password(None, typed)  # same work as a real check
    user = db.get(User, match.user_id) if match is not None else None
    if match is None or user is None or user.status != STATUS_ACTIVE:
        limits.record_wrong_try(db, ATTEMPT_SETUP_CODE, device_id=device.device_id, address=address, now=now)
        after = limits.setup_code_state(db, device_id=device.device_id, now=now)
        raise SetupCodeError(401, "wrong_code", WRONG_CODE, tries_left=after.tries_left if after.allowed else 0)
    account = db.get(UserAccount, user.user_id)
    return Redeemed(make_ticket(match.code_id, user.user_id), user.user_id, user.full_name,
                    account.username if account is not None and account.pin_hash else None)


def complete(db: Session, device: Device | None, *, ticket: str, pin: str, pin_confirm: str,
             consent: bool = False, username: str | None = None, mobile_number: str | None = None,
             now: datetime | None = None):
    """Set the new PIN (and, for a first account, the username and mobile number); signs in."""
    from app.accounts import service  # service imports nothing from here
    now = now or utc_now()
    if device is None:
        raise SetupCodeError(400, "device_required", "Open IrisClick Desktop on this computer, then try again.")
    code_id, user_id = read_ticket(ticket)
    row = db.get(SetupCode, code_id)
    user = db.get(User, user_id)
    if (row is None or row.user_id != user_id or row.used_at is not None or as_utc(row.expires_at) <= now
            or user is None or user.status != STATUS_ACTIVE):
        raise SetupCodeError(401, "ticket_expired", TICKET_EXPIRED)
    account = db.get(UserAccount, user_id)
    first_account = account is None or account.pin_hash is None
    mobile = account.mobile_number if account is not None else None
    if first_account:
        if consent is not True:
            raise SetupCodeError(400, "consent_required", service.MESSAGES["consent_required"])
        problem = usernames.check_username(db, username)
        if problem is not None:
            extra = {"suggestions": usernames.suggestions(db, username)} if problem == usernames.TAKEN else {}
            raise SetupCodeError(409 if problem == usernames.TAKEN else 422, problem, service.MESSAGES[problem], **extra)
        mobile = mobiles.normalize_mobile(mobile_number)
        if mobile is None:
            raise SetupCodeError(422, "bad_mobile", service.MESSAGES["bad_mobile"])
    problem = pins.pin_problem(pin, mobile)
    if problem is not None:
        raise SetupCodeError(422, problem, service.MESSAGES[problem])
    if pin != pin_confirm:
        raise SetupCodeError(422, "pin_mismatch", service.MESSAGES["pin_mismatch"])
    if account is None:
        account = UserAccount(user_id=user_id, created_at=now, signup_source=SIGNUP_ADMIN)
        db.add(account)
    if first_account:
        account.username, account.username_key = username, usernames.username_key(username)
        account.mobile_number, account.consent_at = mobile, now
        log_activity("consent_given", f"{username} accepted the Privacy Notice and Consent Form", user_id, session=db)
    account.pin_hash, account.pin_set_at, account.must_reset_pin = pins.hash_pin(pin), now, False
    row.used_at = now
    log_activity("pin_created", f"{account.username} set a PIN with a setup code", user_id, session=db)
    db.flush()
    limits.clear_wrong_tries(db, user_id=user_id)  # commits
    return service.sign_in(db, device, user_id=None, username=account.username, pin=pin, now=now)
