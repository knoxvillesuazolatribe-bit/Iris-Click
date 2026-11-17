"""Sending a text message (file 07, Phase 5): one small interface and two adapters.

TextBee sends from the SIM of an Android phone running the TextBee app (the owner's own
number); Semaphore is a paid gateway that needs an approved sender name.

Settings (server/.env or Vercel, never in code or logs):
    SMS_PROVIDER            "textbee" or "semaphore"; empty = textbee when TEXTBEE_API_KEY is set
    TEXTBEE_API_KEY         the TextBee API key; empty = TextBee is not set up
    TEXTBEE_DEVICE_ID       optional, the phone to send from; empty = TextBee's default phone
    SEMAPHORE_API_KEY       the Semaphore API key; empty = Semaphore is not set up
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
# TextBee (adviser/owner choice): texts go out from the owner's phone through the TextBee app.
TEXTBEE_URL = "https://api.textbee.dev/api/v1/gateway/send-sms"
PROVIDER_ENV, TEXTBEE_KEY_ENV, TEXTBEE_DEVICE_ENV = "SMS_PROVIDER", "TEXTBEE_API_KEY", "TEXTBEE_DEVICE_ID"
TEXTBEE, SEMAPHORE = "textbee", "semaphore"


class SmsError(Exception):
    """A text was not sent. ``reason``: not_configured | not_allowed | no_sender_name |
    limit_reached | no_phone | failed."""

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


def provider() -> str:
    """Which adapter sends: SMS_PROVIDER, else TextBee when its key is set, else Semaphore."""
    chosen = _setting(PROVIDER_ENV).lower()
    if chosen in (TEXTBEE, SEMAPHORE):
        return chosen
    return TEXTBEE if _setting(TEXTBEE_KEY_ENV) else SEMAPHORE


def provider_name() -> str:
    return "TextBee" if provider() == TEXTBEE else "Semaphore"


def configured() -> bool:
    """SMS can be sent: the chosen adapter has a key (and this is not a test run without a fake sender)."""
    if _test_sender is not None:
        return True
    key = TEXTBEE_KEY_ENV if provider() == TEXTBEE else KEY_ENV
    return bool(_setting(key)) and not _under_tests()


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


def _textbee(number: str, text: str) -> None:
    body = {"recipients": [number], "message": text}  # TextBee wants +63... (international form)
    device = _setting(TEXTBEE_DEVICE_ENV)
    if device:
        body["deviceId"] = device
    try:
        response = requests.post(TEXTBEE_URL, json=body, timeout=TIMEOUT_S,
                                 headers={"x-api-key": _setting(TEXTBEE_KEY_ENV)})
        answer = response.json() if response.content else None
    except (requests.RequestException, ValueError) as exc:
        logger.warning("SMS not sent: %s", type(exc).__name__)  # never the key, number or text
        raise SmsError("failed") from exc
    data = answer.get("data") if isinstance(answer, dict) else None
    ok = (response.status_code in (200, 201) and isinstance(data, dict)
          and data.get("success") is not False and not data.get("failureCount"))
    if not ok:
        logger.warning("SMS not sent: TextBee answered %s", response.status_code)
        if response.status_code == 429:  # the plan's daily or monthly limit is used up
            raise SmsError("limit_reached")
        if response.status_code == 400:  # no enabled phone, or the text could not reach the phone
            raise SmsError("no_phone")
        raise SmsError("failed")
    if isinstance(data.get("warning"), dict):
        logger.warning("TextBee: %s", data["warning"].get("code"))  # e.g. SMS_PERMISSION_MISSING


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
    if provider() == TEXTBEE:
        _textbee(normalized, text)
    else:
        _semaphore(normalized, text)
