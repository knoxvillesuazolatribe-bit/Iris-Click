"""The assistive user signed in on this computer.

IrisClick serves one person at a time on one PC; calibrations, screenshots and
logs made on the server are credited to whoever is set here. Selecting a name
tile sets it and signing out clears it. It is also saved to
storage/active_user.json so it survives a server restart and so the tracking
worker (a separate process) can read it.
"""

import json
import logging
import threading
from pathlib import Path

from app.config import STORAGE_DIR

logger = logging.getLogger("irisclick.active_user")

_lock = threading.Lock()
_path: Path = STORAGE_DIR / "active_user.json"
_loaded = False
_user_id: int | None = None


def use_path(path: Path) -> None:
    """Point at another file (tests); the next read reloads from it."""
    global _path, _loaded, _user_id
    with _lock:
        _path, _loaded, _user_id = path, False, None


def get_user_id() -> int | None:
    global _loaded, _user_id
    with _lock:
        if not _loaded:
            _user_id = _read(_path)
            _loaded = True
        return _user_id


def set_user_id(user_id: int | None) -> None:
    global _loaded, _user_id
    with _lock:
        _user_id, _loaded = user_id, True
        _write(_path, user_id)


def clear_if(user_id: int) -> None:
    """Sign out ``user_id`` here, unless someone else was selected since."""
    if get_user_id() == user_id:
        set_user_id(None)


def _read(path: Path) -> int | None:
    try:
        value = json.loads(path.read_text("utf-8")).get("user_id")
    except FileNotFoundError:
        return None
    except (OSError, ValueError, AttributeError) as exc:
        logger.warning("Active user file unreadable, ignoring it: %s", exc)
        return None
    return value if isinstance(value, int) else None


def _write(path: Path, user_id: int | None) -> None:
    try:
        if user_id is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"user_id": user_id}), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning("Active user not saved to %s: %s", path, exc)
