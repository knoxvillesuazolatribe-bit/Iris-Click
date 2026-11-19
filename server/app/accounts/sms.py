"""Sending a text message (file 07, Phase 5): one small interface and two adapters.

iProg SMS (the owner's choice) is a Philippine gateway: no phone is needed. Its shared sender
reaches Globe, TM, DITO and GOMO; Smart and TNT need an approved sender name. Semaphore is
the earlier adapter, kept for setups that still use it.

Settings (server/.env or Vercel, never in code or logs):
    SMS_PROVIDER            "iprog" or "semaphore"; empty = iProg when IPROG_API_TOKEN is set
    IPROG_API_TOKEN         the iProg SMS API token; empty = iProg is not set up
    SEMAPHORE_API_KEY       the Semaphore API key; empty = Semaphore is not set up
    SEMAPHORE_SENDER_NAME   optional, an approved sender name; empty = Semaphore's default
    SMS_ONLY_TO             testing lock: while set, texts go ONLY to this number (comma list allowed)

Safety: nothing is ever texted while pytest runs; tests pass their own fake sender.
SOS alerts to contacts without an email use this module too (app/services/sos_delivery.py).
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
# iProg SMS (owner's choice): a Philippine gateway, no phone needed.
IPROG_URL = "https://www.iprogsms.com/api/v1/sms_messages"
PROVIDER_ENV, IPROG_TOKEN_ENV = "SMS_PROVIDER", "IPROG_API_TOKEN"
IPROG, SEMAPHORE = "iprog", "semaphore"
NAMES = {IPROG: "iProg SMS", SEMAPHORE: "Semaphore"}
KEYS = {IPROG: IPROG_TOKEN_ENV, SEMAPHORE: KEY_ENV}


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
    """Tests only: route texts to ``send(number, text)`` instead of a real gateway."""
    global _test_sender
    _test_sender = send
    try:
        yield
    finally:
        _test_sender = None


def provider() -> str:
    """Which adapter sends: SMS_PROVIDER, else iProg when its token is set, else Semaphore."""
    chosen = _setting(PROVIDER_ENV).lower()
    if chosen in KEYS:
        return chosen
    return IPROG if _setting(IPROG_TOKEN_ENV) else SEMAPHORE


def provider_name() -> str:
    return NAMES[provider()]


def configured() -> bool:
    """SMS can be sent: the chosen adapter has a key (and this is not a test run without a fake sender)."""
    if _test_sender is not None:
        return True
    return bool(_setting(KEYS[provider()])) and not _under_tests()


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


def _iprog(number: str, text: str) -> None:
    # The token goes in the JSON body (never in the URL, so it stays out of logs); iProg takes 639...
    body = {"api_token": _setting(IPROG_TOKEN_ENV), "phone_number": number.lstrip("+"), "message": text}
    try:
        response = requests.post(IPROG_URL, json=body, timeout=TIMEOUT_S)
        answer = response.json() if response.content else None
    except (requests.RequestException, ValueError) as exc:
        logger.warning("SMS not sent: %s", type(exc).__name__)  # never the token, number or text
        raise SmsError("failed") from exc
    # iProg answers HTTP 200 with its own status in the body: 200 and a message id when queued.
    ok = (response.status_code == 200 and isinstance(answer, dict)
          and str(answer.get("status")) == "200" and answer.get("message_id"))
    if not ok:
        logger.warning("SMS not sent: iProg answered %s / %s", response.status_code,
                       answer.get("status") if isinstance(answer, dict) else None)
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
    {IPROG: _iprog, SEMAPHORE: _semaphore}[provider()](normalized, text)
