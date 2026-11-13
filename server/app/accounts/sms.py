"""Sending a text message (file 07, Phase 5): one small interface and one adapter, Semaphore.

Settings (server/.env or Vercel, never in code or logs):
    SEMAPHORE_API_KEY       the Semaphore API key; empty = SMS is not set up
    SEMAPHORE_SENDER_NAME   optional, an approved sender name; empty = Semaphore's default
    SMS_ONLY_TO             testing lock: while set, texts go ONLY to this number (comma list allowed)

Safety: nothing is ever texted while pytest runs; tests pass their own fake sender.
The SOS "SMS" stub (app/services/sos_delivery.py) is not changed by this module.
"""

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import requests
from dotenv import dotenv_values

from app.accounts import mobiles
from app.config import SERVER_DIR

logger = logging.getLogger("irisclick.sms")

SEMAPHORE_URL = "https://api.semaphore.co/api/v4/messages"
TIMEOUT_S = 15
KEY_ENV, SENDER_ENV, ONLY_TO_ENV = "SEMAPHORE_API_KEY", "SEMAPHORE_SENDER_NAME", "SMS_ONLY_TO"


class SmsError(Exception):
    """A text was not sent. ``reason``: not_configured | not_allowed | no_sender_name | failed."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _setting(name: str, env_file: Path = SERVER_DIR / ".env") -> str:
    value = os.environ.get(name)
    if value is None:
        try:
            value = dotenv_values(env_file).get(name)
        except OSError:
            value = None
    return (value or "").strip()


def _under_tests() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ


_test_sender: Callable[[str, str], None] | None = None


@contextmanager
def fake_sender(send: Callable[[str, str], None]) -> Iterator[None]:
    """Tests only: route texts to ``send(number, text)`` instead of Semaphore."""
    global _test_sender
    _test_sender = send
    try:
        yield
    finally:
        _test_sender = None


def configured() -> bool:
    """SMS can be sent: a key is set (and this is not a test run without a fake sender)."""
    if _test_sender is not None:
        return True
    return bool(_setting(KEY_ENV)) and not _under_tests()


def only_to() -> list[str]:
    """The testing lock's numbers (+639...), or [] when anyone may be texted."""
    numbers = [mobiles.normalize_mobile(part) for part in _setting(ONLY_TO_ENV).split(",") if part.strip()]
    return [n for n in numbers if n]


def allowed(number: str) -> bool:
    lock = only_to()
    return not lock or mobiles.normalize_mobile(number) in lock


def _local(number: str) -> str:
    """+639178082488 -> 09178082488 (the form Semaphore documents)."""
    return "0" + number[3:] if number.startswith("+63") else number


def _semaphore(number: str, text: str) -> None:
    data = {"apikey": _setting(KEY_ENV), "number": _local(number), "message": text}
    sender = _setting(SENDER_ENV)
    if sender:
        data["sendername"] = sender
    try:
        response = requests.post(SEMAPHORE_URL, data=data, timeout=TIMEOUT_S)
        body = response.json() if response.content else None
    except (requests.RequestException, ValueError) as exc:
        logger.warning("SMS not sent: %s", type(exc).__name__)  # never the key, number or text
        raise SmsError("failed") from exc
    ok = (response.status_code == 200 and isinstance(body, list) and body
          and all(str(m.get("status", "")).lower() not in ("failed", "refunded") for m in body if isinstance(m, dict)))
    if not ok:
        logger.warning("SMS not sent: Semaphore answered %s", response.status_code)
        # Semaphore refuses every text until the account has an approved sender name (found in the live test).
        if isinstance(body, list) and any(isinstance(m, dict) and "senderName" in m for m in body):
            raise SmsError("no_sender_name")
        raise SmsError("failed")


def send(number: str, text: str) -> None:
    """Text ``number`` (+639...). Raises SmsError; never pretends a text was sent."""
    normalized = mobiles.normalize_mobile(number)
    if normalized is None:
        raise SmsError("not_allowed")
    if not allowed(normalized):
        logger.info("SMS not sent: the number is not in SMS_ONLY_TO (testing lock)")
        raise SmsError("not_allowed")
    if _test_sender is not None:
        _test_sender(normalized, text)
        return
    if not configured():
        raise SmsError("not_configured")
    _semaphore(normalized, text)
