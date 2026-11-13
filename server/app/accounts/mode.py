"""Which assistive sign-in IrisClick uses: ``ASSISTIVE_SIGNIN_MODE``.

    legacy           (default) today's name tiles, admin-created users, unchanged
    device_accounts  accounts on this computer: self sign-up, username + PIN

Set it in the hosted server's environment (Vercel) or in server/.env. Read on
every call, so switching back to "legacy" works at once; the new tables and their
data stay, so switching forward again loses nothing. Anything unexpected = legacy.
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values

from app.config import SERVER_DIR

ENV_NAME = "ASSISTIVE_SIGNIN_MODE"
LEGACY, DEVICE_ACCOUNTS = "legacy", "device_accounts"
Mode = Literal["legacy", "device_accounts"]


def signin_mode(env_file: Path = SERVER_DIR / ".env") -> Mode:
    value = os.environ.get(ENV_NAME)
    if value is None:
        try:
            value = dotenv_values(env_file).get(ENV_NAME)
        except OSError:
            value = None
    return DEVICE_ACCOUNTS if (value or "").strip().lower() == DEVICE_ACCOUNTS else LEGACY


def device_accounts_on() -> bool:
    try:
        return signin_mode() == DEVICE_ACCOUNTS
    except Exception:  # noqa: BLE001 - anything odd means today's behaviour
        return False
