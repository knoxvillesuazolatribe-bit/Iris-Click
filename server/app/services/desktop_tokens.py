"""Signed tokens that link a signed-in user on the hosted website to their IrisClick Desktop.

    link token     5 minutes, made by the hosted server for the signed-in user; the page
                   hands it to the desktop app on 127.0.0.1.
    desktop token  12 hours, given to the desktop app in exchange for a link token; the
                   desktop app uses it for the hosted API (database option 2), so the
                   Supabase password never leaves the hosted server.

Tokens are HMAC-SHA256 signed with IRISCLICK_DESKTOP_SECRET, or, when that is not
set, a key derived from the database password (which only the hosted server has).
No new table: a token carries the user id, its kind and its expiry.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from app.config import get_settings

LINK = "link"
DESKTOP = "desktop"
LIFETIME_S = {LINK: 5 * 60, DESKTOP: 12 * 3600}
SECRET_ENV = "IRISCLICK_DESKTOP_SECRET"
MIN_SECRET = 32


class TokenError(Exception):
    pass


def _key() -> bytes:
    secret = os.environ.get(SECRET_ENV, "").strip()
    if len(secret) >= MIN_SECRET:
        return secret.encode()
    db_password = get_settings().db_password.get_secret_value()
    if not db_password:
        raise TokenError("IrisClick Desktop linking is not set up on this server.")
    return hashlib.sha256(b"irisclick-desktop-v1:" + db_password.encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make(kind: str, user_id: int, now: float | None = None) -> tuple[str, int]:
    """(token, expires_at as Unix seconds)."""
    issued = int(now if now is not None else time.time())
    expires = issued + LIFETIME_S[kind]
    payload = _b64(json.dumps({"k": kind, "u": user_id, "e": expires, "n": secrets.token_hex(8)},
                              separators=(",", ":")).encode())
    signature = _b64(hmac.new(_key(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}", expires


def read(token: str, kind: str, now: float | None = None) -> int:
    """The user id in a valid, unexpired token of ``kind``; raises TokenError otherwise."""
    try:
        payload, signature = token.split(".", 1)
        expected = _b64(hmac.new(_key(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise TokenError("bad signature")
        data = json.loads(_unb64(payload))
    except TokenError:
        raise
    except Exception as exc:  # noqa: BLE001 - any malformed token is simply invalid
        raise TokenError("malformed") from exc
    if data.get("k") != kind or not isinstance(data.get("u"), int):
        raise TokenError("wrong kind")
    if (now if now is not None else time.time()) >= data.get("e", 0):
        raise TokenError("expired")
    return data["u"]
