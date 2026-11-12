"""Routes that belong to the old sign-in only (plan section 3, H1-H11, and A4).

With ``ASSISTIVE_SIGNIN_MODE=device_accounts`` people make and manage their own
accounts on their computer, so the admin routes that did it for them, and the
"pick your name, no PIN" sign-in, answer 403. In legacy mode (the default) these
checks do nothing, so every existing route and test behaves exactly as before.

Use on a decorator line:  ``dependencies=[Depends(legacy_only(PEOPLE_CREATE))]``
"""

from collections.abc import Callable

from fastapi import HTTPException

from app.accounts import mode

CODE = "device_accounts"

PEOPLE_CREATE = "People create their own accounts now."
PEOPLE_SET = "People set this themselves on their computer now."
NO_GLOBAL_DEFAULTS = "Global defaults are not edited with accounts on this computer."
ADDED_ON_COMPUTER = "Accounts are added on each computer now."
USE_YOUR_PIN = "Choose your account on this computer and enter your PIN."


def legacy_only(message: str) -> Callable[[], None]:
    """A dependency that refuses the route while accounts on this computer are on."""

    def check() -> None:
        if mode.device_accounts_on():
            raise HTTPException(status_code=403, detail=message, headers={"X-IrisClick-Code": CODE})

    return check
