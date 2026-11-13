"""D1 (file 07): the online copy may open without the site access code.

The access code exists because the old sign-in ("pick your name") had no password. With
accounts on this computer every person has a username and PIN, admins a password, and the
no-PIN name sign-in is closed (accounts/guards.py). So the code is no longer needed, and
PDAO can drop it by removing IRISCLICK_ACCESS_CODE.

Opens ONLY when both are true:
    ASSISTIVE_SIGNIN_MODE=device_accounts   and   no IRISCLICK_ACCESS_CODE set.
Legacy mode never opens without a code; a code that is set is always required.
"""

from app.accounts import mode


def open_without_code() -> bool:
    from app.cloud import access  # access imports this module inside its functions only
    return mode.device_accounts_on() and access.configured_code() is None
