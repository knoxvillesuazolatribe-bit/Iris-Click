"""Admin password hashing with Argon2id (team decision D6)."""

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_ADMIN_PASSWORD_LENGTH = 12

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """True when ``password`` matches; never raises for a bad or missing hash."""
    if not password_hash:
        # Same work as a real check, so a wrong email is not faster to detect.
        _verify_quietly(_dummy_hash(), password)
        return False
    return _verify_quietly(password_hash, password)


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


def _verify_quietly(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache
def _dummy_hash() -> str:
    return _hasher.hash("irisclick-timing-equaliser")
