"""Admin sign-in (Fig. 17): email + password, retry on invalid, lockout on repeats.

Every attempt writes a system_logs row: ``login`` or ``login_failed``.
"""

import threading
import time
from collections import deque

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import ROLE_ADMIN, STATUS_ACTIVE, User
from app.services.password_hashing import hash_password, needs_rehash, verify_password
from app.services.system_log_service import log_activity

MAX_FAILURES = 5
FAILURE_WINDOW_S = 600.0
LOCKOUT_S = 300.0

INVALID_MESSAGE = "Email or password is incorrect."
INACTIVE_MESSAGE = "This account is inactive. Contact the PDAO administrator."


class AuthError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class LoginThrottle:
    """Locks an email for LOCKOUT_S after MAX_FAILURES within FAILURE_WINDOW_S."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def seconds_locked(self, key: str) -> float:
        with self._lock:
            return max(0.0, self._locked_until.get(key, 0.0) - self._clock())

    def failed(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            recent = self._failures.setdefault(key, deque())
            recent.append(now)
            while recent and now - recent[0] > FAILURE_WINDOW_S:
                recent.popleft()
            if len(recent) >= MAX_FAILURES:
                self._locked_until[key] = now + LOCKOUT_S
                recent.clear()

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)


throttle = LoginThrottle()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def authenticate_admin(db: Session, email: str, password: str) -> User:
    """The active admin for these credentials (logs the attempt); raises AuthError."""
    key = normalize_email(email)
    locked_s = throttle.seconds_locked(key)
    if locked_s > 0:
        minutes = max(1, round(locked_s / 60))
        log_activity("login_failed", f"Admin sign-in blocked for {key}: too many attempts")
        raise AuthError(429, f"Too many attempts. Try again in {minutes} minute(s).")

    user = db.scalars(select(User).where(User.email == key, User.role == ROLE_ADMIN)).first()
    if not verify_password(user.password_hash if user else None, password):
        throttle.failed(key)
        log_activity("login_failed", f"Admin sign-in failed for {key}",
                     user.user_id if user else None)
        raise AuthError(401, INVALID_MESSAGE)
    if user.status != STATUS_ACTIVE:
        log_activity("login_failed", f"Inactive admin {key} tried to sign in", user.user_id)
        raise AuthError(403, INACTIVE_MESSAGE)

    throttle.succeeded(key)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    log_activity("login", f"Admin {user.full_name} signed in", user.user_id, session=db)
    return user
