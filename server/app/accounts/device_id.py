"""This computer's ID, kept by IrisClick Desktop in storage/device_id.txt.

A random value made on first use: it is not built from the hardware, the Windows
account or anything personal, and deleting the file simply makes this a "new"
computer (accounts must be added to it again). The hosted server never stores it,
only its SHA-256 (see devices.py).
"""

import os
import re
import secrets
import threading
from pathlib import Path

from app.config import STORAGE_DIR

DEVICE_ID_PATH = STORAGE_DIR / "device_id.txt"
DEVICE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,64}")
_lock = threading.Lock()


def is_device_id(value: object) -> bool:
    return isinstance(value, str) and DEVICE_ID_PATTERN.fullmatch(value) is not None


def _read(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    return value if is_device_id(value) else None


def this_computer_id(path: Path | None = None) -> str:
    """The saved ID, or a new one (saved) when the file is missing or damaged."""
    path = path or DEVICE_ID_PATH
    with _lock:
        saved = _read(path)
        if saved is not None:
            return saved
        value = secrets.token_urlsafe(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        draft = path.with_suffix(".tmp")
        draft.write_text(value, encoding="ascii")
        os.replace(draft, path)
        return value
