"""Server-side sessions behind the httpOnly ``irisclick_session`` cookie.

The cookie holds a random token; the database keeps only its SHA-256, an
expiry and a revoked time. A session counts only while it is unexpired,
unrevoked and its user is still active, so deactivating a user signs them out.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.timestamps import as_utc, utc_now
from app.models.user import ROLE_ADMIN, ROLE_ASSISTIVE_USER, STATUS_ACTIVE, User
from app.models.user_session import UserSession

COOKIE_NAME = "irisclick_session"
COOKIE_PATH = "/api"
SESSION_HOURS = {ROLE_ADMIN: 8, ROLE_ASSISTIVE_USER: 12}


@dataclass(frozen=True)
class SignedIn:
    session: UserSession
    user: User


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_max_age_s(role: str) -> int:
    return SESSION_HOURS[role] * 3600


def create_session(db: Session, user: User) -> str:
    """Add a session for ``user`` (caller commits); returns the cookie token."""
    token = secrets.token_urlsafe(32)
    now = utc_now()
    db.add(UserSession(token_hash=hash_token(token), user_id=user.user_id, role=user.role,
                       created_at=now, expires_at=now + timedelta(hours=SESSION_HOURS[user.role])))
    return token


def resolve(db: Session, token: str | None) -> SignedIn | None:
    """The live session and its active user for ``token``, or None."""
    if not token:
        return None
    row = db.scalars(select(UserSession).where(UserSession.token_hash == hash_token(token))).first()
    if row is None or row.revoked_at is not None or as_utc(row.expires_at) <= utc_now():
        return None
    user = db.get(User, row.user_id)
    if user is None or user.status != STATUS_ACTIVE or user.role != row.role:
        return None
    return SignedIn(row, user)


def revoke(db: Session, token: str | None) -> UserSession | None:
    """Mark the session for ``token`` revoked (caller commits); returns it if found."""
    if not token:
        return None
    row = db.scalars(select(UserSession).where(UserSession.token_hash == hash_token(token))).first()
    if row is not None and row.revoked_at is None:
        row.revoked_at = utc_now()
    return row
