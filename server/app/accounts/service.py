"""Accounts on this computer: tiles, sign-up, sign-in, remove and "ask for my PIN again".

Everything is tied to a computer (a ``devices`` row found from the ID IrisClick
Desktop keeps). Callers commit nothing themselves: each function here commits.
Log lines never contain a PIN, a code or a mobile number.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts import limits, mobiles, pins, usernames
from app.config import get_settings
from app.models.account_models import SIGNUP_SELF, Device, DeviceAccount, UserAccount
from app.models.calibration_record import CalibrationRecord
from app.models.timestamps import as_utc, utc_now
from app.models.user import ROLE_ASSISTIVE_USER, STATUS_ACTIVE, User
from app.services import active_user
from app.services.system_log_service import log_activity

REMEMBER_DAYS = 30

MESSAGES = {
    "device_required": "Open IrisClick Desktop on this computer, then try again.",
    "consent_required": "Please accept the Privacy Notice and Consent Form first.",
    usernames.TOO_SHORT: "Use 3 to 20 letters, numbers, _ or .",
    usernames.TOO_LONG: "Use 3 to 20 letters, numbers, _ or .",
    usernames.BAD_CHARACTERS: "Use only letters, numbers, _ and .",
    usernames.NEEDS_LETTER: "Your username needs at least one letter.",
    usernames.BAD_EDGES: "Start and end your username with a letter or a number.",
    usernames.RESERVED_NAME: "That username is not allowed. Try another.",
    usernames.NOT_ALLOWED: "That username is not allowed. Try another.",
    usernames.TAKEN: "That username is taken. Try another.",
    "bad_mobile": "Enter a mobile number like 0917 123 4567.",
    "mobile_limit": "That mobile number is already used by 3 accounts. Use another number.",
    pins.NOT_SIX_DIGITS: "Your PIN is 6 numbers.",
    pins.TOO_EASY: "That PIN is too easy. Choose another.",
    "pin_mismatch": "The PINs don't match. Try again.",
    "signup_limit": "Too many new accounts were made on this computer today. Try again tomorrow.",
    "wrong_pin": "Username or PIN is incorrect.",
    "pin_required": "Enter your PIN.",
    "wait": "Too many wrong tries. Please wait, then try again.",
    "reset_needed": "Too many wrong tries. Use Forgot PIN, or ask your PDAO administrator to reset your PIN.",
    "not_on_this_computer": "That account is not on this computer.",
}


class AccountError(Exception):
    """A refusal the website can explain: HTTP status, a stable code, a plain message, extra facts."""

    def __init__(self, status_code: int, code: str, **extra):
        super().__init__(code)
        self.status_code, self.code, self.extra = status_code, code, extra
        self.message = MESSAGES[code]


@dataclass(frozen=True)
class Tile:
    user_id: int
    username: str
    needs_pin: bool
    # The latest successful calibration's accuracy percentage; None before the first one.
    accuracy: float | None = None


@dataclass(frozen=True)
class SignedInAccount:
    user: User
    username: str
    newly_added: bool = field(default=False, compare=False)


def _remember_days() -> int:
    return int(getattr(get_settings(), "remember_days", REMEMBER_DAYS))


def _remembered(link: DeviceAccount, device: Device, now: datetime) -> bool:
    return (link.remembered and not device.is_shared and link.remembered_until is not None
            and as_utc(link.remembered_until) > now)


def _link(db: Session, device: Device, user_id: int) -> DeviceAccount | None:
    return db.scalar(select(DeviceAccount).where(DeviceAccount.device_id == device.device_id,
                                                 DeviceAccount.user_id == user_id))


def _active(db: Session, user_id: int) -> User | None:
    user = db.get(User, user_id)
    return user if user is not None and user.role == ROLE_ASSISTIVE_USER and user.status == STATUS_ACTIVE else None


def list_tiles(db: Session, device: Device | None, now: datetime | None = None) -> list[Tile]:
    """The active accounts added to this computer, most recently used first."""
    if device is None:
        return []
    now = now or utc_now()
    rows = db.execute(
        select(DeviceAccount, UserAccount).join(UserAccount, UserAccount.user_id == DeviceAccount.user_id)
        .join(User, User.user_id == DeviceAccount.user_id)
        .where(DeviceAccount.device_id == device.device_id, DeviceAccount.removed_at.is_(None),
               User.status == STATUS_ACTIVE, User.role == ROLE_ASSISTIVE_USER, UserAccount.pin_hash.is_not(None))
        .order_by(DeviceAccount.last_used_at.desc().nulls_last(), UserAccount.username_key)).all()
    accuracy = _latest_accuracy(db, [account.user_id for _, account in rows])
    return [Tile(account.user_id, account.username, not _remembered(link, device, now), accuracy.get(account.user_id))
            for link, account in rows]


def _latest_accuracy(db: Session, user_ids: list[int]) -> dict[int, float]:
    """Each person's most recent successful calibration accuracy (the percentage on the tile)."""
    found: dict[int, float] = {}
    if not user_ids:
        return found
    rows = db.execute(
        select(CalibrationRecord.user_id, CalibrationRecord.accuracy_score)
        .where(CalibrationRecord.user_id.in_(user_ids), CalibrationRecord.status == "Successful",
               CalibrationRecord.accuracy_score.is_not(None))
        .order_by(CalibrationRecord.calibration_date.desc(), CalibrationRecord.calibration_id.desc())).all()
    for user_id, score in rows:
        found.setdefault(user_id, float(score))
    return found


def _use_on(db: Session, device: Device, user_id: int, remember: bool | None, now: datetime) -> bool:
    """Put the account on this computer (again) and note it was just used. True when newly added."""
    link = _link(db, device, user_id)
    added = link is None or link.removed_at is not None
    if link is None:
        link = DeviceAccount(device_id=device.device_id, user_id=user_id, created_at=now)
        db.add(link)
    link.removed_at = None
    link.last_used_at = now
    if remember is not None:
        link.remembered = bool(remember) and not device.is_shared
    link.remembered_until = now + timedelta(days=_remember_days()) if link.remembered else None
    return added


def sign_up(db: Session, device: Device | None, *, consent: bool, username: str, mobile_number: str, pin: str,
            pin_confirm: str, remember: bool = False, now: datetime | None = None) -> SignedInAccount:
    now = now or utc_now()
    if device is None:
        raise AccountError(400, "device_required")
    if consent is not True:
        raise AccountError(400, "consent_required")
    problem = usernames.check_username(db, username)
    if problem is not None:
        extra = {"suggestions": usernames.suggestions(db, username)} if problem == usernames.TAKEN else {}
        raise AccountError(409 if problem == usernames.TAKEN else 422, problem, **extra)
    mobile = mobiles.normalize_mobile(mobile_number)
    if mobile is None:
        raise AccountError(422, "bad_mobile")
    if not limits.mobile_allowed(db, mobile, per_mobile=int(getattr(get_settings(), "accounts_per_mobile",
                                                                    limits.ACCOUNTS_PER_MOBILE))):
        raise AccountError(409, "mobile_limit")
    problem = pins.pin_problem(pin, mobile)
    if problem is not None:
        raise AccountError(422, problem)
    if pin != pin_confirm:
        raise AccountError(422, "pin_mismatch")
    if not limits.signup_allowed(db, device.device_id, now=now, per_day=int(getattr(
            get_settings(), "signups_per_device_per_day", limits.SIGNUPS_PER_DEVICE_PER_DAY))):
        raise AccountError(429, "signup_limit")
    user = User(full_name=username, role=ROLE_ASSISTIVE_USER)
    db.add(user)
    try:
        db.flush()
        db.add(UserAccount(user_id=user.user_id, username=username, username_key=usernames.username_key(username),
                           mobile_number=mobile, pin_hash=pins.hash_pin(pin), pin_set_at=now, consent_at=now,
                           signup_source=SIGNUP_SELF, created_at=now))
        _use_on(db, device, user.user_id, remember, now)
        db.flush()
    except IntegrityError as exc:  # someone took the username a moment ago
        db.rollback()
        raise AccountError(409, usernames.TAKEN, suggestions=usernames.suggestions(db, username)) from exc
    for kind, text in (("account_created", f"{username} created an account"),
                       ("consent_given", f"{username} accepted the Privacy Notice and Consent Form"),
                       ("pin_created", f"{username} created a PIN"),
                       ("account_added_to_device", f"{username} was added to computer #{device.device_id}")):
        log_activity(kind, text, user.user_id, session=db)
    db.commit()
    active_user.set_user_id(user.user_id)  # this computer's person, as picking a name tile does
    return SignedInAccount(user, username, True)


def _refuse(state: limits.TryState) -> AccountError:
    if state.status == limits.RESET_NEEDED:
        return AccountError(423, "reset_needed")
    return AccountError(429, "wait", wait_seconds=state.wait_seconds)


def _check_pin(db: Session, device: Device, account: UserAccount | None, pin: object, address: str | None,
               now: datetime, *, say_tries_left: bool) -> None:
    """Raise unless ``pin`` is this account's PIN; counts wrong tries. ``account`` is None for unknown names."""
    user_id = account.user_id if account is not None else None
    state = limits.pin_state(db, device_id=device.device_id, user_id=user_id, address=address, now=now)
    if account is not None and account.must_reset_pin:
        state = limits.TryState(limits.RESET_NEEDED)
    correct = pins.verify_pin(account.pin_hash if account is not None else None, pin)  # same work either way
    if not state.allowed:
        raise _refuse(state)
    if correct:
        return
    limits.record_wrong_try(db, device_id=device.device_id, user_id=user_id, address=address, now=now)
    after = limits.pin_state(db, device_id=device.device_id, user_id=user_id, address=address, now=now)
    if account is not None:
        name = account.username
        log_activity("pin_failed", f"Wrong PIN for {name} on computer #{device.device_id}", user_id, session=db)
        if not after.allowed:
            log_activity("pin_locked", f"{name} is locked on computer #{device.device_id} ({after.status})",
                         user_id, session=db)
        db.commit()
    if say_tries_left and account is not None:
        if not after.allowed:
            raise _refuse(after)
        raise AccountError(401, "wrong_pin", tries_left=after.tries_left)
    raise AccountError(401, "wrong_pin")


def sign_in(db: Session, device: Device | None, *, user_id: int | None = None, username: str | None = None,
            pin: str | None = None, remember: bool | None = None, address: str | None = None,
            now: datetime | None = None) -> SignedInAccount:
    """A tile on this computer (``user_id``) or "I already have an account" (``username`` + PIN)."""
    now = now or utc_now()
    if device is None:
        raise AccountError(400, "device_required")
    by_tile = user_id is not None
    if by_tile:
        link = _link(db, device, user_id)
        account = db.get(UserAccount, user_id) if link is not None and link.removed_at is None else None
        if account is None or account.pin_hash is None or _active(db, user_id) is None:
            raise AccountError(404, "not_on_this_computer")
        if pin is None:
            if not _remembered(link, device, now):
                raise AccountError(401, "pin_required")
        else:
            _check_pin(db, device, account, pin, address, now, say_tries_left=True)
    else:
        key = usernames.username_key(username or "")
        account = db.scalar(select(UserAccount).where(UserAccount.username_key == key)) if key else None
        if account is not None and (account.pin_hash is None or _active(db, account.user_id) is None):
            account = None
        _check_pin(db, device, account, pin, address, now, say_tries_left=False)
    limits.clear_wrong_tries(db, user_id=account.user_id, device_id=device.device_id)
    added = _use_on(db, device, account.user_id, remember if pin is not None else None, now)
    if added:
        log_activity("account_added_to_device", f"{account.username} was added to computer #{device.device_id}",
                     account.user_id, session=db)
    log_activity("user_selected", f"{account.username} signed in" + (" with their PIN" if pin is not None else
                                                                    " (remembered on this computer)"),
                 account.user_id, session=db)
    db.commit()
    active_user.set_user_id(account.user_id)  # this computer's person, as picking a name tile does
    return SignedInAccount(db.get(User, account.user_id), account.username, added)


def remove_from_computer(db: Session, device: Device | None, *, user_id: int, pin: str | None = None,
                         address: str | None = None, now: datetime | None = None) -> None:
    """Forget the account on this computer; the account itself stays. A shared computer asks for the PIN."""
    now = now or utc_now()
    if device is None:
        raise AccountError(400, "device_required")
    link = _link(db, device, user_id)
    account = db.get(UserAccount, user_id)
    if link is None or link.removed_at is not None or account is None:
        raise AccountError(404, "not_on_this_computer")
    if device.is_shared:
        if pin is None:
            raise AccountError(401, "pin_required")
        _check_pin(db, device, account, pin, address, now, say_tries_left=True)
    link.removed_at, link.remembered, link.remembered_until = now, False, None
    log_activity("account_removed_from_device", f"{account.username} was removed from computer #{device.device_id}",
                 user_id, session=db)
    db.commit()


def forget_remember_me(db: Session, device: Device | None, user_id: int) -> None:
    """Sign out: this computer asks for the PIN next time."""
    link = _link(db, device, user_id) if device is not None else None
    if link is not None:
        link.remembered, link.remembered_until = False, None
        db.commit()
