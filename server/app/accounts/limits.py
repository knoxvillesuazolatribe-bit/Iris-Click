"""Wrong-try limits for PINs and setup codes, and the open sign-up limits.

Every wrong try is a row in ``pin_attempts``, so the limits hold on every Vercel
instance and survive restarts. Nothing here stores a PIN, a code or a visitor's
address (only a SHA-256 of the address).

PIN, per account on one computer:   5 wrong -> wait 5 minutes; 10 wrong -> the PIN
                                    must be reset (Forgot PIN or the administrator).
PIN, per account everywhere:        20 wrong in an hour -> wait (slows guessing from
                                    many computers; never forces a reset, so nobody
                                    can lock another person out for good).
Per computer / per visitor address: 30 / 60 wrong in an hour -> wait (covers tries
                                    with usernames that do not exist).
Setup code:                         5 wrong per computer in 15 minutes, 30 in an
                                    hour for the whole site -> wait.
A correct PIN clears that account's wrong tries on that computer.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.account_models import ATTEMPT_PIN, ATTEMPT_SETUP_CODE, DeviceAccount, PinAttempt, UserAccount
from app.models.timestamps import utc_now

PIN_TRIES_BEFORE_WAIT = 5
PIN_WAIT = timedelta(minutes=5)
PIN_TRIES_BEFORE_RESET = 10
PIN_TRIES_PER_HOUR_EVERYWHERE = 20
TRIES_PER_HOUR_PER_DEVICE = 30
TRIES_PER_HOUR_PER_ADDRESS = 60
SETUP_CODE_TRIES_PER_DEVICE = 5
SETUP_CODE_DEVICE_WINDOW = timedelta(minutes=15)
SETUP_CODE_TRIES_PER_HOUR_SITE = 30
HOUR = timedelta(hours=1)
SIGNUPS_PER_DEVICE_PER_DAY = 5
ACCOUNTS_PER_MOBILE = 3

OK, WAIT, RESET_NEEDED = "ok", "wait", "reset_needed"


@dataclass(frozen=True)
class TryState:
    status: str = OK          # ok | wait | reset_needed
    tries_left: int = 0       # wrong tries left before the next wait or reset (when ok)
    wait_seconds: int = 0     # how long to wait (when status is wait)

    @property
    def allowed(self) -> bool:
        return self.status == OK


def address_hash(address: str | None) -> str | None:
    return hashlib.sha256(address.encode("utf-8")).hexdigest() if address else None


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)  # SQLite returns naive UTC


def _seconds_until(moment: datetime, now: datetime) -> int:
    return max(1, int((_aware(moment) - now).total_seconds()) + 1)


def record_wrong_try(db: Session, kind: str = ATTEMPT_PIN, *, device_id: int | None = None,
                     user_id: int | None = None, address: str | None = None,
                     now: datetime | None = None) -> None:
    db.add(PinAttempt(device_id=device_id, user_id=user_id, kind=kind, address_hash=address_hash(address),
                      attempted_at=now or utc_now()))
    db.commit()


def clear_wrong_tries(db: Session, *, user_id: int, device_id: int | None = None) -> None:
    """After a correct PIN (that computer only), or an admin Unlock / PIN reset (every computer)."""
    query = delete(PinAttempt).where(PinAttempt.user_id == user_id, PinAttempt.kind == ATTEMPT_PIN)
    if device_id is not None:
        query = query.where(PinAttempt.device_id == device_id)
    db.execute(query)
    db.commit()


def _window(db: Session, kind: str, since: datetime, limit: int, now: datetime, *conditions) -> TryState | None:
    """A wait state when ``limit`` wrong tries happened since ``since``; the wait ends when the oldest ages out."""
    times = db.scalars(select(PinAttempt.attempted_at).where(PinAttempt.kind == kind, PinAttempt.attempted_at >= since,
                                                             *conditions).order_by(PinAttempt.attempted_at)).all()
    if len(times) < limit:
        return None
    return TryState(WAIT, 0, _seconds_until(_aware(times[len(times) - limit]) + (now - since), now))


def pin_state(db: Session, *, device_id: int | None, user_id: int | None, address: str | None = None,
              now: datetime | None = None) -> TryState:
    """May a PIN be tried now? ``user_id`` is None for a username that does not exist."""
    now = now or utc_now()
    hour_ago = now - HOUR
    waits = []
    if device_id is not None:
        waits.append(_window(db, ATTEMPT_PIN, hour_ago, TRIES_PER_HOUR_PER_DEVICE, now,
                             PinAttempt.device_id == device_id))
    if address:
        waits.append(_window(db, ATTEMPT_PIN, hour_ago, TRIES_PER_HOUR_PER_ADDRESS, now,
                             PinAttempt.address_hash == address_hash(address)))
    tries_left = PIN_TRIES_BEFORE_WAIT
    if user_id is not None:
        waits.append(_window(db, ATTEMPT_PIN, hour_ago, PIN_TRIES_PER_HOUR_EVERYWHERE, now,
                             PinAttempt.user_id == user_id))
        here = [PinAttempt.user_id == user_id, PinAttempt.kind == ATTEMPT_PIN,
                PinAttempt.device_id == device_id if device_id is not None else PinAttempt.device_id.is_(None)]
        wrong = db.scalar(select(func.count()).select_from(PinAttempt).where(*here)) or 0
        if wrong >= PIN_TRIES_BEFORE_RESET:
            return TryState(RESET_NEEDED)
        if wrong >= PIN_TRIES_BEFORE_WAIT:
            fifth = db.scalars(select(PinAttempt.attempted_at).where(*here).order_by(PinAttempt.attempted_at)
                               .offset(PIN_TRIES_BEFORE_WAIT - 1).limit(1)).one()
            if _aware(fifth) + PIN_WAIT > now:
                return TryState(WAIT, 0, _seconds_until(_aware(fifth) + PIN_WAIT, now))
            tries_left = PIN_TRIES_BEFORE_RESET - wrong
        else:
            tries_left = PIN_TRIES_BEFORE_WAIT - wrong
    waits = [w for w in waits if w is not None]
    if waits:
        return max(waits, key=lambda w: w.wait_seconds)
    return TryState(OK, tries_left)


def setup_code_state(db: Session, *, device_id: int | None, now: datetime | None = None) -> TryState:
    now = now or utc_now()
    waits = [_window(db, ATTEMPT_SETUP_CODE, now - HOUR, SETUP_CODE_TRIES_PER_HOUR_SITE, now)]
    left = SETUP_CODE_TRIES_PER_DEVICE
    if device_id is not None:
        since = now - SETUP_CODE_DEVICE_WINDOW
        waits.append(_window(db, ATTEMPT_SETUP_CODE, since, SETUP_CODE_TRIES_PER_DEVICE, now,
                             PinAttempt.device_id == device_id))
        left -= db.scalar(select(func.count()).select_from(PinAttempt).where(
            PinAttempt.kind == ATTEMPT_SETUP_CODE, PinAttempt.device_id == device_id,
            PinAttempt.attempted_at >= since)) or 0
    waits = [w for w in waits if w is not None]
    if waits:
        return max(waits, key=lambda w: w.wait_seconds)
    return TryState(OK, max(left, 0))


def signup_allowed(db: Session, device_id: int, *, per_day: int = SIGNUPS_PER_DEVICE_PER_DAY,
                   now: datetime | None = None) -> bool:
    """Fewer than ``per_day`` new accounts were created on this computer in the last 24 hours."""
    since = (now or utc_now()) - timedelta(days=1)
    made = db.scalar(select(func.count()).select_from(DeviceAccount).join(
        UserAccount, UserAccount.user_id == DeviceAccount.user_id).where(
        DeviceAccount.device_id == device_id, DeviceAccount.created_at >= since,
        UserAccount.created_at >= since)) or 0
    return made < per_day


def mobile_allowed(db: Session, mobile_number: str, *, per_mobile: int = ACCOUNTS_PER_MOBILE) -> bool:
    """Fewer than ``per_mobile`` accounts already use this mobile number."""
    used = db.scalar(select(func.count()).select_from(UserAccount).where(
        UserAccount.mobile_number == mobile_number)) or 0
    return used < per_mobile
