"""Philippine mobile numbers for PIN recovery: stored as +639XXXXXXXXX, shown masked."""

import re

MOBILE = re.compile(r"\+639\d{9}")


def normalize_mobile(text: object) -> str | None:
    """``0917 808 2488``, ``639178082488`` or ``+63 917-808-2488`` -> ``+639178082488``; None if not a mobile."""
    if not isinstance(text, str):
        return None
    digits = re.sub(r"[\s\-().]", "", text.strip())
    if digits.startswith("+"):
        digits = digits[1:]
    if not digits.isdigit():
        return None
    if digits.startswith("09") and len(digits) == 11:
        digits = "63" + digits[1:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "63" + digits
    number = "+" + digits
    return number if MOBILE.fullmatch(number) else None


def mask_mobile(number: str | None) -> str:
    """``+639178082488`` -> ``09** *** 2488``: only the last four digits are ever shown."""
    if not number or MOBILE.fullmatch(number) is None:
        return ""
    return f"09** *** {number[-4:]}"
