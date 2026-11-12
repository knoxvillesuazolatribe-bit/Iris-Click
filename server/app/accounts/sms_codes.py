"""6-digit codes by text (file 07, Phase 5): verify a mobile number, and Forgot PIN.

Rules (file 07, section F): a code expires in 10 minutes and allows 5 tries; a number gets
at most 3 texts an hour and 5 a day; "Resend" after 60 seconds. Codes are Argon2 hashes;
the number is kept only as an HMAC. Logs never hold a code or a full number.

It never pretends a code was sent: if the text fails, nothing is saved and the caller
shows "We couldn't send a code. Ask PDAO staff to reset your PIN."
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.accounts import limits, mobiles, pins, sms
from app.models.account_models import Device, DeviceAccount, UserAccount
from app.models.sms_models import PURPOSE_RESET, PURPOSE_VERIFY, SmsCode
from app.models.timestamps import as_utc, utc_now
from app.models.user import STATUS_ACTIVE, User
from app.services import password_hashing, session_service
from app.services.system_log_service import log_activity

CODE_DIGITS = 6
CODE_LIFETIME = timedelta(minutes=10)
TRIES_PER_CODE = 5
RESEND_AFTER = timedelta(seconds=60)
TEXTS_PER_HOUR = 3
TEXTS_PER_DAY = 5
TICKET_LIFETIME_S = 15 * 60

CANT_SEND = "We couldn't send a code. Ask PDAO staff to reset your PIN."
MESSAGES = {
    "sms_off": "We can't text you yet. If you forget your PIN, ask PDAO staff.",
    "cant_send": CANT_SEND,
    "bad_mobile": "Enter a mobile number like 0917 123 4567.",
    "resend_wait": "Please wait a moment before asking for another code.",
    "sms_limit": "Too many codes were sent to this number. Try again later, or ask PDAO staff.",
    "no_code": "That code has expired. Ask for a new one.",
    "wrong_code": "That code is not right.",
    "too_many_tries": "Too many wrong codes. Ask for a new one.",
    "ticket_expired": "This took too long. Please start again.",
    "not_found": "That account is not on this computer.",
}
TEXTS = {
    PURPOSE_VERIFY: "IrisClick: your code is {code}. It expires in 10 minutes. Do not share it with anyone.",
    PURPOSE_RESET: ("IrisClick: your code to reset your PIN is {code}. It expires in 10 minutes. "
                    "If you did not ask for it, ignore this message."),
}


class SmsCodeError(Exception):
    def __init__(self, status_code: int, code: str, **extra):
        super().__init__(code)
        self.status_code, self.code, self.extra = status_code, code, extra
        self.message = MESSAGES.get(code, CANT_SEND)


@dataclass(frozen=True)
class Sent:
    to: str                 # masked: 09** *** 2488
    resend_after: int       # seconds


# ---------- keys and tickets ----------

def _key(label: bytes) -> bytes:
    from app.services import desktop_tokens
    return hashlib.sha256(label + desktop_tokens._key()).digest()  # noqa: SLF001


def mobile_hash(number: str) -> str:
    return hmac.new(_key(b"irisclick-mobile-v1:"), number.encode(), hashlib.sha256).hexdigest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_ticket(kind: str, user_id: int, number_hash: str, now: float | None = None) -> str:
    expires = int(now if now is not None else time.time()) + TICKET_LIFETIME_S
    payload = _b64(json.dumps({"k": kind, "u": user_id, "m": number_hash, "e": expires},
                              separators=(",", ":")).encode())
    return payload + "." + _b64(hmac.new(_key(b"irisclick-sms-ticket-v1:"), payload.encode(), hashlib.sha256).digest())


def read_ticket(kind: str, ticket: object, now: float | None = None) -> tuple[int, str]:
    """(user_id, mobile_hash) from a valid ticket of this ``kind``; raises SmsCodeError."""
    try:
        payload, signature = str(ticket).split(".", 1)
        expected = _b64(hmac.new(_key(b"irisclick-sms-ticket-v1:"), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data["k"] != kind or (now if now is not None else time.time()) >= int(data["e"]):
            raise ValueError("wrong kind or expired")
        return int(data["u"]), str(data["m"])
    except Exception as exc:  # noqa: BLE001 - any broken ticket is simply invalid
        raise SmsCodeError(401, "ticket_expired") from exc


# ---------- sending and checking ----------

def _recent(db: Session, number_hash: str, since: datetime) -> int:
    return db.scalar(select(func.count()).select_from(SmsCode).where(
        SmsCode.mobile_hash == number_hash, SmsCode.created_at >= since)) or 0


def send_code(db: Session, *, purpose: str, number: str, user_id: int | None = None,
              device_id: int | None = None, now: datetime | None = None) -> Sent:
    """Text a fresh code to ``number`` (+639...). Raises SmsCodeError; saves nothing unless sent."""
    now = now or utc_now()
    if not sms.configured():
        raise SmsCodeError(503, "sms_off" if purpose == PURPOSE_VERIFY else "cant_send")
    number_hash = mobile_hash(number)
    last = db.scalars(select(SmsCode.created_at).where(SmsCode.mobile_hash == number_hash)
                      .order_by(SmsCode.created_at.desc()).limit(1)).first()
    if last is not None and as_utc(last) + RESEND_AFTER > now:
        wait = int((as_utc(last) + RESEND_AFTER - now).total_seconds()) + 1
        raise SmsCodeError(429, "resend_wait", wait_seconds=wait)
    if (_recent(db, number_hash, now - timedelta(hours=1)) >= TEXTS_PER_HOUR
            or _recent(db, number_hash, now - timedelta(days=1)) >= TEXTS_PER_DAY):
        raise SmsCodeError(429, "sms_limit")
    code = "".join(secrets.choice("0123456789") for _ in range(CODE_DIGITS))
    try:
        sms.send(number, TEXTS[purpose].format(code=code))
    except sms.SmsError as exc:
        raise SmsCodeError(503, "sms_off" if exc.reason == "not_configured" and purpose == PURPOSE_VERIFY
                           else "cant_send") from exc
    db.execute(update(SmsCode).where(SmsCode.mobile_hash == number_hash, SmsCode.purpose == purpose,
                                     SmsCode.used_at.is_(None)).values(used_at=now))
    db.add(SmsCode(user_id=user_id, device_id=device_id, mobile_hash=number_hash, purpose=purpose,
                   code_hash=password_hashing.hash_password(code), attempts=0,
                   expires_at=now + CODE_LIFETIME, created_at=now))
    if purpose == PURPOSE_RESET:
        log_activity("pin_reset_sms_sent", "A code to reset the PIN was texted", user_id, session=db)
    db.commit()
    return Sent(mobiles.mask_mobile(number), int(RESEND_AFTER.total_seconds()))


def check_code(db: Session, *, purpose: str, number: str, code: object, now: datetime | None = None) -> SmsCode:
    """The matching code row, marked used. Raises SmsCodeError (wrong code counts a try)."""
    now = now or utc_now()
    row = db.scalars(select(SmsCode).where(SmsCode.mobile_hash == mobile_hash(number), SmsCode.purpose == purpose,
                                           SmsCode.used_at.is_(None))
                     .order_by(SmsCode.created_at.desc()).limit(1)).first()
    if row is None or as_utc(row.expires_at) <= now:
        raise SmsCodeError(410, "no_code")
    if row.attempts >= TRIES_PER_CODE:
        raise SmsCodeError(429, "too_many_tries")
    text = str(code or "").strip()
    if not (text.isdigit() and len(text) == CODE_DIGITS and password_hashing.verify_password(row.code_hash, text)):
        row.attempts += 1
        db.commit()
        left = TRIES_PER_CODE - row.attempts
        if left <= 0:
            raise SmsCodeError(429, "too_many_tries")
        raise SmsCodeError(401, "wrong_code", tries_left=left)
    row.used_at = now
    db.commit()
    return row


# ---------- verify a mobile number (sign-up, setup code) ----------

def send_verify(db: Session, device: Device | None, mobile_number: object) -> Sent:
    number = mobiles.normalize_mobile(mobile_number)
    if number is None:
        raise SmsCodeError(422, "bad_mobile")
    return send_code(db, purpose=PURPOSE_VERIFY, number=number, device_id=device.device_id if device else None)


def verify_mobile(db: Session, mobile_number: object, code: object) -> str:
    """A 15-minute ticket saying this number was verified (used after the account exists)."""
    number = mobiles.normalize_mobile(mobile_number)
    if number is None:
        raise SmsCodeError(422, "bad_mobile")
    check_code(db, purpose=PURPOSE_VERIFY, number=number, code=code)
    return make_ticket(PURPOSE_VERIFY, 0, mobile_hash(number))


def confirm_mobile(db: Session, user_id: int, ticket: object, now: datetime | None = None) -> bool:
    """Mark the signed-in person's number verified if the ticket is for that same number."""
    _, number_hash = read_ticket(PURPOSE_VERIFY, ticket)
    account = db.get(UserAccount, user_id)
    if account is None or not account.mobile_number or mobile_hash(account.mobile_number) != number_hash:
        return False
    account.mobile_verified_at = now or utc_now()
    log_activity("mobile_verified", f"{account.username} verified their mobile number", user_id, session=db)
    db.commit()
    return True


# ---------- Forgot PIN ----------

def _account_on_device(db: Session, device: Device | None, user_id: int) -> UserAccount:
    if device is None:
        raise SmsCodeError(400, "not_found")
    link = db.scalars(select(DeviceAccount).where(DeviceAccount.device_id == device.device_id,
                                                  DeviceAccount.user_id == user_id,
                                                  DeviceAccount.removed_at.is_(None))).first()
    account = db.get(UserAccount, user_id)
    user = db.get(User, user_id)
    if link is None or account is None or user is None or user.status != STATUS_ACTIVE:
        raise SmsCodeError(404, "not_found")
    return account


def forgot_send(db: Session, device: Device | None, user_id: int) -> Sent:
    account = _account_on_device(db, device, user_id)
    if not account.mobile_number or account.mobile_verified_at is None:
        raise SmsCodeError(409, "cant_send")  # only a verified number gets a reset code
    return send_code(db, purpose=PURPOSE_RESET, number=account.mobile_number, user_id=user_id,
                     device_id=device.device_id)


def forgot_verify(db: Session, device: Device | None, user_id: int, code: object) -> str:
    account = _account_on_device(db, device, user_id)
    if not account.mobile_number:
        raise SmsCodeError(409, "cant_send")
    check_code(db, purpose=PURPOSE_RESET, number=account.mobile_number, code=code)
    return make_ticket(PURPOSE_RESET, user_id, mobile_hash(account.mobile_number))


def forgot_complete(db: Session, device: Device | None, ticket: object, pin: str, pin_confirm: str,
                    now: datetime | None = None) -> UserAccount:
    """Set the new PIN: wrong tries cleared, every other session of the account signed out."""
    from app.accounts import service  # service imports nothing from here
    now = now or utc_now()
    user_id, number_hash = read_ticket(PURPOSE_RESET, ticket)
    account = _account_on_device(db, device, user_id)
    if not account.mobile_number or mobile_hash(account.mobile_number) != number_hash:
        raise SmsCodeError(401, "ticket_expired")
    problem = pins.pin_problem(pin, account.mobile_number)
    if problem is not None:
        raise service.AccountError(422, problem)
    if pin != pin_confirm:
        raise service.AccountError(422, "pin_mismatch")
    account.pin_hash, account.pin_set_at, account.must_reset_pin = pins.hash_pin(pin), now, False
    session_service.revoke_all_for_user(db, user_id)
    log_activity("pin_reset_by_sms", f"{account.username} chose a new PIN with a code sent by text", user_id,
                 session=db)
    db.flush()
    limits.clear_wrong_tries(db, user_id=user_id)  # commits
    return account
