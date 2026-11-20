"""SOS email through Brevo's API (used whenever BREVO_API_KEY is set)."""

import pytest
import requests
from pydantic import SecretStr

from app.config import get_settings
from app.services import sos_delivery
from app.services.sos_delivery import (
    BREVO_BUSY,
    BREVO_KEY_REFUSED,
    BREVO_URL,
    CANNOT_REACH,
    DeliveryError,
    EmailSender,
)

KEY = "xkeysib-test-key"


def settings(**overrides):
    values = {"brevo_api_key": SecretStr(KEY), "smtp_host": "", "smtp_username": "",
              "smtp_from": "IrisClick <irisclickph@gmail.com>", "smtp_timeout_s": 15.0}
    values.update(overrides)
    return get_settings().model_copy(update=values)


class Answer:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


class Calls(list):
    script: list


@pytest.fixture
def posts(monkeypatch):
    calls = Calls()
    script = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        outcome = script.pop(0) if script else Answer(201, {"messageId": "<1@brevo>"})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(sos_delivery.requests, "post", post)
    calls.script = script
    return calls


def test_sends_through_brevo_with_the_irisclick_sender(posts):
    EmailSender(settings()).send("maria@example.com", "SOS from Juan", "Please call Juan.")
    assert len(posts) == 1
    call = posts[0]
    assert call["url"] == BREVO_URL and call["timeout"] == 15.0
    assert call["headers"]["api-key"] == KEY
    assert call["json"] == {"sender": {"name": "IrisClick", "email": "irisclickph@gmail.com"},
                            "to": [{"email": "maria@example.com"}], "subject": "SOS from Juan",
                            "textContent": "Please call Juan."}
    assert KEY not in call["url"]


def test_a_plain_address_sender_has_no_name(posts):
    EmailSender(settings(smtp_from="", smtp_username="irisclickph@gmail.com")).send("a@b.co", "S", "B")
    assert posts[0]["json"]["sender"] == {"email": "irisclickph@gmail.com"}


def test_brevo_needs_no_smtp_server():
    sender = EmailSender(settings())
    assert sender.uses_brevo and sender.configured()


def test_without_a_key_smtp_is_used_as_before():
    sender = EmailSender(settings(brevo_api_key=SecretStr(""), smtp_host="smtp.gmail.com"))
    assert not sender.uses_brevo and sender.configured()


def test_brevo_without_a_sender_is_not_set_up():
    assert not EmailSender(settings(smtp_from="", smtp_username="")).configured()


def test_a_refused_key_is_not_retried(posts, caplog):
    posts.script.append(Answer(401, {"code": "unauthorized", "message": "Key not found"}))
    with caplog.at_level("WARNING", logger="irisclick.sos"), pytest.raises(DeliveryError) as caught:
        EmailSender(settings()).send("a@b.co", "S", "B")
    assert caught.value.message == BREVO_KEY_REFUSED and caught.value.retryable is False
    assert "HTTP 401 Key not found" in caplog.text and KEY not in caplog.text


def test_an_unverified_sender_says_why(posts):
    posts.script.append(Answer(400, {"code": "invalid_parameter", "message": "Sender is not valid"}))
    with pytest.raises(DeliveryError) as caught:
        EmailSender(settings()).send("a@b.co", "S", "B")
    assert caught.value.message == "Brevo refused the email: Sender is not valid."
    assert caught.value.retryable is False


@pytest.mark.parametrize("status", [429, 500, 503])
def test_busy_or_down_brevo_is_retried(posts, status):
    posts.script.append(Answer(status))
    with pytest.raises(DeliveryError) as caught:
        EmailSender(settings()).send("a@b.co", "S", "B")
    assert caught.value.message == BREVO_BUSY and caught.value.retryable is True


def test_no_connection_to_brevo_is_retried(posts):
    posts.script.append(requests.ConnectionError("offline"))
    with pytest.raises(DeliveryError) as caught:
        EmailSender(settings()).send("a@b.co", "S", "B")
    assert caught.value.message == f"{CANNOT_REACH} (ConnectionError)"
    assert caught.value.retryable is True
