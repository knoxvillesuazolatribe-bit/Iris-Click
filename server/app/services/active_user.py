"""The assistive user signed in on this computer.

IrisClick serves one person at a time on one PC; calibrations, screenshots and
logs made on the server are credited to whoever is set here. The sign-in flow
(Phase 2) sets it; until then it stays None and rows have no user.
"""

import threading

_lock = threading.Lock()
_user_id: int | None = None


def get_user_id() -> int | None:
    with _lock:
        return _user_id


def set_user_id(user_id: int | None) -> None:
    global _user_id
    with _lock:
        _user_id = user_id
