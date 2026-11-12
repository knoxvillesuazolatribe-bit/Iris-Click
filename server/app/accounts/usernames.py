"""Username rules for accounts on this computer.

3 to 20 characters from letters, numbers, ``_`` and ``.`` (the keys on the gaze
username keyboard). Usernames are unique without regard to case: ``username_key``
is the lower-case form stored next to the name as typed.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account_models import UserAccount
from app.services import word_filter_service

USERNAME_MIN, USERNAME_MAX = 3, 20
ALLOWED = re.compile(r"[A-Za-z0-9_.]*")
SEPARATORS = "_."
# Names that would look like staff or the system on a tile.
RESERVED = frozenset({"admin", "administrator", "irisclick", "pdao", "staff", "support", "system", "root"})

TOO_SHORT, TOO_LONG, BAD_CHARACTERS = "too_short", "too_long", "bad_characters"
NEEDS_LETTER, BAD_EDGES, RESERVED_NAME = "needs_letter", "bad_edges", "reserved"
NOT_ALLOWED, TAKEN = "not_allowed", "taken"


def username_key(username: str) -> str:
    return username.strip().lower()


def username_problem(username: object) -> str | None:
    """Why this cannot be a username (a code for the website to explain), or None when it can."""
    if not isinstance(username, str) or len(username) < USERNAME_MIN:
        return TOO_SHORT
    if len(username) > USERNAME_MAX:
        return TOO_LONG
    if ALLOWED.fullmatch(username) is None:
        return BAD_CHARACTERS
    if not any(c.isalpha() for c in username):
        return NEEDS_LETTER
    if username[0] in SEPARATORS or username[-1] in SEPARATORS:
        return BAD_EDGES
    if username_key(username).strip(SEPARATORS + "0123456789") in RESERVED or username_key(username) in RESERVED:
        return RESERVED_NAME
    return None


def is_offensive(db: Session, username: str) -> bool:
    """True when the word filter would mask the name, also when it is split by ``_`` or ``.``."""
    spaced = username.replace("_", " ").replace(".", " ")
    joined = username.replace("_", "").replace(".", "")
    return any(word_filter_service.check(db, form).was_filtered for form in {username, spaced, joined})


def is_taken(db: Session, username: str) -> bool:
    return db.scalar(select(UserAccount.user_id).where(UserAccount.username_key == username_key(username))) is not None


def check_username(db: Session, username: object) -> str | None:
    """The full check for sign-up: rules, word filter, then whether it is free."""
    problem = username_problem(username)
    if problem is not None:
        return problem
    if is_offensive(db, username):
        return NOT_ALLOWED
    return TAKEN if is_taken(db, username) else None


def suggestions(db: Session, username: str, count: int = 3) -> list[str]:
    """Free, valid names close to a taken one, e.g. mari_lapu -> mari_lapu2, mari_lapu_2, mari.lapu2."""
    base = username.rstrip(SEPARATORS + "0123456789") or username
    found: list[str] = []
    for number in range(2, 100):
        for form in (f"{base}{number}", f"{base}_{number}", f"{base}.{number}"):
            candidate = form if len(form) <= USERNAME_MAX else base[:USERNAME_MAX - len(str(number))] + str(number)
            if candidate in found or username_key(candidate) == username_key(username):
                continue
            if check_username(db, candidate) is None:
                found.append(candidate)
                if len(found) == count:
                    return found
    return found
