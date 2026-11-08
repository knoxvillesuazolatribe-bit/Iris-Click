"""Computer lock for the website: which assistive users may sign in on this computer.

Turned on in Vercel with IRISCLICK_COMPUTER_LOCK=on. A helper approves a
computer once for a person, either with a one-time approval link (24 hours)
opened on that computer, or with "Approve this computer" while signed in as
admin on it. The browser then keeps a computer key in a cookie; the name
screen only lists the people approved for that key.
"""

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.approved_computer import ApprovedComputer
from app.models.timestamps import as_utc, utc_now
from app.models.user import ROLE_ASSISTIVE_USER, STATUS_ACTIVE, User
from app.services.system_log_service import log_activity

LOCK_ENV = "IRISCLICK_COMPUTER_LOCK"
LINK_LIFETIME = timedelta(hours=24)
MAX_LABEL = 80
DEFAULT_LABEL = "Computer"
KEY_PATTERN_LENGTHS = range(40, 65)  # token_urlsafe(32) is 43 characters

STATUS_APPROVED = "approved"
STATUS_WAITING = "waiting"
STATUS_EXPIRED = "expired"

LINK_NOT_VALID = ("This approval link has expired or was already used. "
                  "Ask your helper or the PDAO office for a new one.")
USER_GONE = "This account is not active any more. Ask your PDAO administrator."
NOT_FOUND = "That computer was not found."


class ComputerError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def lock_on() -> bool:
    return os.environ.get(LOCK_ENV, "").strip().lower() in {"1", "on", "true", "yes"}


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def usable_key(cookie: str | None) -> str | None:
    """A computer key from the cookie, or None when there is none (or it looks wrong)."""
    if cookie and len(cookie) in KEY_PATTERN_LENGTHS and cookie.replace("-", "").replace("_", "").isalnum():
        return cookie
    return None


def clean_label(label: str | None) -> str:
    text = " ".join((label or "").split())[:MAX_LABEL]
    return text or DEFAULT_LABEL


def _assistive_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.role != ROLE_ASSISTIVE_USER:
        raise ComputerError(404, "That user was not found.")
    return user


@dataclass(frozen=True)
class ComputerView:
    computer_id: int
    label: str
    status: str
    created_at: datetime
    approved_at: datetime | None
    last_used_at: datetime | None
    code_expires_at: datetime | None
    this_computer: bool


def status_of(row: ApprovedComputer, now: datetime) -> str:
    if row.key_hash:
        return STATUS_APPROVED
    expires = as_utc(row.code_expires_at)
    return STATUS_WAITING if expires and expires > now else STATUS_EXPIRED


def list_for_user(db: Session, user_id: int, key: str | None) -> list[ComputerView]:
    """The person's approved computers and waiting links, newest first (removed ones hidden)."""
    _assistive_user(db, user_id)
    now = utc_now()
    key_hash = hash_secret(key) if key else None
    rows = db.scalars(
        select(ApprovedComputer)
        .where(ApprovedComputer.user_id == user_id, ApprovedComputer.removed_at.is_(None))
        .order_by(ApprovedComputer.created_at.desc(), ApprovedComputer.computer_id.desc())
    ).all()
    return [ComputerView(
        computer_id=row.computer_id, label=row.label, status=status_of(row, now),
        created_at=as_utc(row.created_at), approved_at=as_utc(row.approved_at),
        last_used_at=as_utc(row.last_used_at), code_expires_at=as_utc(row.code_expires_at),
        this_computer=bool(key_hash and row.key_hash == key_hash),
    ) for row in rows]


def make_link(db: Session, user_id: int, label: str | None, admin: User) -> tuple[str, datetime]:
    """A one-time approval code for the person (valid 24 hours). The caller commits."""
    user = _assistive_user(db, user_id)
    code = new_secret()
    expires = utc_now() + LINK_LIFETIME
    db.add(ApprovedComputer(user_id=user.user_id, label=clean_label(label), code_hash=hash_secret(code),
                            code_expires_at=expires, created_by=admin.user_id))
    log_activity("computer_link_made", f"Approval link made for {user.full_name}", admin.user_id,
                 session=db)
    return code, expires


def _approve(db: Session, user: User, key: str, row: ApprovedComputer | None, label: str,
             created_by: int | None) -> ApprovedComputer:
    """Approves key for user, reusing an approval this computer already has for them."""
    now = utc_now()
    key_hash = hash_secret(key)
    existing = db.scalars(
        select(ApprovedComputer).where(ApprovedComputer.user_id == user.user_id,
                                       ApprovedComputer.key_hash == key_hash,
                                       ApprovedComputer.removed_at.is_(None))
    ).first()
    if existing is not None:
        if row is not None:
            row.code_hash = None
            row.removed_at = now  # the link is used up; this computer was already approved
        existing.last_used_at = now
        return existing
    if row is None:
        row = ApprovedComputer(user_id=user.user_id, label=label, created_by=created_by)
        db.add(row)
    row.key_hash = key_hash
    row.code_hash = None
    row.code_expires_at = None
    row.approved_at = now
    row.last_used_at = now
    return row


def approve_here(db: Session, user_id: int, label: str | None, admin: User,
                 key: str | None) -> tuple[ApprovedComputer, str]:
    """"Approve this computer": the admin is on the person's computer. The caller commits
    and sets the cookie to the returned key."""
    user = _assistive_user(db, user_id)
    if user.status != STATUS_ACTIVE:
        raise ComputerError(409, USER_GONE)
    key = key or new_secret()
    row = _approve(db, user, key, None, clean_label(label), admin.user_id)
    log_activity("computer_approved", f"Computer approved for {user.full_name} by an admin",
                 admin.user_id, session=db)
    return row, key


def claim(db: Session, code: str, key: str | None) -> tuple[User, str]:
    """Opens an approval link on this computer. The caller commits and sets the cookie."""
    now = utc_now()
    row = db.scalars(
        select(ApprovedComputer).where(ApprovedComputer.code_hash == hash_secret(code.strip()))
    ).first()
    if row is None or row.removed_at is not None or row.key_hash or status_of(row, now) != STATUS_WAITING:
        raise ComputerError(401, LINK_NOT_VALID)
    user = db.get(User, row.user_id)
    if user is None or user.role != ROLE_ASSISTIVE_USER or user.status != STATUS_ACTIVE:
        raise ComputerError(409, USER_GONE)
    key = key or new_secret()
    _approve(db, user, key, row, row.label, row.created_by)
    log_activity("computer_approved", f"Computer approved for {user.full_name} with a link",
                 user.user_id, session=db)
    return user, key


def remove(db: Session, user_id: int, computer_id: int, admin: User) -> None:
    """Removes an approved computer or waiting link. The caller commits."""
    user = _assistive_user(db, user_id)
    row = db.get(ApprovedComputer, computer_id)
    if row is None or row.user_id != user_id or row.removed_at is not None:
        raise ComputerError(404, NOT_FOUND)
    row.removed_at = utc_now()
    row.code_hash = None
    log_activity("computer_removed", f"Computer \"{row.label}\" removed for {user.full_name}",
                 admin.user_id, session=db)


def approved_user_ids(db: Session, key: str | None) -> set[int]:
    """Who may sign in on the computer with this key."""
    if not key:
        return set()
    rows = db.scalars(
        select(ApprovedComputer).where(ApprovedComputer.key_hash == hash_secret(key),
                                       ApprovedComputer.removed_at.is_(None))
    ).all()
    return {row.user_id for row in rows}


def mark_used(db: Session, key: str, user_id: int) -> None:
    """Notes when a person last signed in on this computer. The caller commits."""
    row = db.scalars(
        select(ApprovedComputer).where(ApprovedComputer.key_hash == hash_secret(key),
                                       ApprovedComputer.user_id == user_id,
                                       ApprovedComputer.removed_at.is_(None))
    ).first()
    if row is not None:
        row.last_used_at = utc_now()
