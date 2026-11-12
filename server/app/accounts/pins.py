"""PIN rules for accounts on this computer: six digits, not an easy pattern, Argon2 only.

A PIN is never stored, logged or returned: ``hash_pin`` gives the Argon2id hash
that goes in ``user_accounts.pin_hash``, and ``verify_pin`` takes the same time
whether or not the account has a PIN, so a wrong username is not faster to spot.
"""

from app.services import password_hashing

PIN_LENGTH = 6
NOT_SIX_DIGITS, TOO_EASY = "not_six_digits", "too_easy"


def is_pin(pin: object) -> bool:
    return isinstance(pin, str) and len(pin) == PIN_LENGTH and pin.isascii() and pin.isdigit()


def _is_run(pin: str) -> bool:
    """123456, 654321, 012345, and runs that wrap past 9 or 0 (789012, 210987)."""
    steps = {(int(b) - int(a)) % 10 for a, b in zip(pin, pin[1:], strict=False)}
    return steps in ({1}, {9})


def _is_easy(pin: str) -> bool:
    return (len(set(pin)) == 1                          # 000000
            or _is_run(pin)                             # 123456, 654321
            or pin[:2] * 3 == pin                       # 121212
            or pin[:3] * 2 == pin                       # 123123
            or all(pin[i] == pin[i + 1] for i in (0, 2, 4)))  # 112233


def pin_problem(pin: object, mobile_number: str | None = None) -> str | None:
    """Why this cannot be the PIN (a code for the website to explain), or None when it can."""
    if not is_pin(pin):
        return NOT_SIX_DIGITS
    if _is_easy(pin) or (mobile_number and mobile_number.endswith(pin)):
        return TOO_EASY
    return None


def hash_pin(pin: str) -> str:
    if not is_pin(pin):
        raise ValueError("A PIN is six digits")
    return password_hashing.hash_password(pin)


def verify_pin(pin_hash: str | None, pin: object) -> bool:
    """True when the PIN matches. Never raises, and does the same work for a missing hash."""
    return password_hashing.verify_password(pin_hash, pin if is_pin(pin) else "")
