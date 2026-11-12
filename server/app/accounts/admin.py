"""What PDAO admins can do with accounts on this computer (build step 14, plan section 3).

Admins never see or set a PIN: Reset PIN makes an 8-digit setup code (setup_codes),
Unlock clears wrong PIN tries, Sign out everywhere ends every session and every
"Remember me". Each function commits and logs (never a PIN, a code or a mobile number).
"""

from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.accounts import limits, mobiles
from app.models.account_models import ATTEMPT_PIN, Device, DeviceAccount, PinAttempt, UserAccount
from app.models.user import ROLE_ASSISTIVE_USER, User
from app.services import active_user, session_service
from app.services.system_log_service import log_activity

# The Logs "Accounts" tab: every activity type the accounts feature writes.
ACCOUNT_LOG_TYPES = ("account_", "pin_", "consent_given", "address_updated", "device_shared_")

LOCK_OK, LOCK_WAIT, LOCK_RESET = "ok", "locked", "needs_new_pin"


@dataclass(frozen=True)
class AccountRow:
    user_id: int
    username: str
    mobile: str            # masked: only the last four digits, e.g. 09** *** 2488
    mobile_verified: bool
    computers: int


@dataclass(frozen=True)
class AccountDetail(AccountRow):
    lock: str              # ok | locked | needs_new_pin
    must_reset_pin: bool
    shared_computers: int


def _computers(db: Session) -> dict[int, int]:
    rows = db.execute(select(DeviceAccount.user_id, func.count()).where(DeviceAccount.removed_at.is_(None))
                      .group_by(DeviceAccount.user_id)).all()
    return {user_id: count for user_id, count in rows}


def _row(account: UserAccount, computers: int) -> AccountRow:
    return AccountRow(account.user_id, account.username, mobiles.mask_mobile(account.mobile_number),
                      account.mobile_verified_at is not None, computers)


def list_accounts(db: Session) -> list[AccountRow]:
    counts = _computers(db)
    accounts = db.scalars(select(UserAccount).order_by(UserAccount.username_key)).all()
    return [_row(account, counts.get(account.user_id, 0)) for account in accounts]


def lock_state(db: Session, user_id: int) -> str:
    """The worst lock on any computer: too many wrong PINs means "locked" (wait) or "needs a new PIN"."""
    counts = db.scalars(select(func.count()).select_from(PinAttempt)
                        .where(PinAttempt.user_id == user_id, PinAttempt.kind == ATTEMPT_PIN)
                        .group_by(PinAttempt.device_id)).all()
    worst = max(counts, default=0)
    if worst >= limits.PIN_TRIES_BEFORE_RESET:
        return LOCK_RESET
    if worst >= limits.PIN_TRIES_BEFORE_WAIT:
        return LOCK_WAIT
    return LOCK_OK


def account_detail(db: Session, user_id: int) -> AccountDetail | None:
    account = db.get(UserAccount, user_id)
    if account is None:
        return None
    links = db.scalars(select(DeviceAccount).where(DeviceAccount.user_id == user_id,
                                                   DeviceAccount.removed_at.is_(None))).all()
    shared = sum(1 for link in links if (device := db.get(Device, link.device_id)) is not None and device.is_shared)
    row = _row(account, len(links))
    return AccountDetail(**row.__dict__, lock=lock_state(db, user_id), must_reset_pin=account.must_reset_pin,
                         shared_computers=shared)


def _person(db: Session, user_id: int) -> User | None:
    user = db.get(User, user_id)
    return user if user is not None and user.role == ROLE_ASSISTIVE_USER else None


def unlock(db: Session, admin: User, user_id: int) -> bool:
    user = _person(db, user_id)
    if user is None:
        return False
    limits.clear_wrong_tries(db, user_id=user_id)
    log_activity("pin_unlocked_by_admin", f"{admin.full_name} unlocked {user.full_name}", user_id, session=db)
    db.commit()
    return True


def sign_out_everywhere(db: Session, admin: User, user_id: int) -> int | None:
    """Ends every session and every "Remember me"; the next sign-in on any computer asks for the PIN."""
    user = _person(db, user_id)
    if user is None:
        return None
    ended = session_service.revoke_all_for_user(db, user_id)
    db.execute(update(DeviceAccount).where(DeviceAccount.user_id == user_id)
               .values(remembered=False, remembered_until=None))
    active_user.clear_if(user_id)
    log_activity("account_signed_out_everywhere", f"{admin.full_name} signed {user.full_name} out everywhere",
                 user_id, session=db)
    db.commit()
    return ended


def set_shared(db: Session, admin: User, device: Device, shared: bool) -> Device:
    """Shared computer: no "Remember me" and sign-out when idle. Turning it on forgets every Remember me here."""
    device.is_shared = bool(shared)
    if device.is_shared:
        db.execute(update(DeviceAccount).where(DeviceAccount.device_id == device.device_id)
                   .values(remembered=False, remembered_until=None))
    log_activity("device_shared_on" if device.is_shared else "device_shared_off",
                 f"{admin.full_name} set computer #{device.device_id} to "
                 f"{'shared' if device.is_shared else 'personal'}", None, session=db)
    db.commit()
    return device
