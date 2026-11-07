"""SOS email over SMTP and the SMS placeholder (Phase 5). No real mail is sent."""

import smtplib

import pytest
from pydantic import SecretStr

from app.config import get_settings
from app.services import sos_delivery
from app.services.sos_delivery import (
    CANNOT_REACH,
    EMAIL_NOT_SET_UP,
    SMS_NOT_SET_UP,
    DeliveryError,
    EmailSender,
    NotConfiguredSms,
)


class FakeSMTP:
    """Stands in for smtplib.SMTP / SMTP_SSL and records what was done."""

    instances: list["FakeSMTP"] = []
    fail_with: Exception | None = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.calls: list = []
        self.sent = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))
        if isinstance(FakeSMTP.fail_with, smtplib.SMTPAuthenticationError):
            raise FakeSMTP.fail_with

    def send_message(self, message):
        if FakeSMTP.fail_with is not None and not isinstance(FakeSMTP.fail_with,
                                                             smtplib.SMTPAuthenticationError):
            raise FakeSMTP.fail_with
        self.sent.append(message)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSMTP.instances, FakeSMTP.fail_with = [], None
    monkeypatch.setattr(sos_delivery.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(sos_delivery.smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


def _settings(**overrides):
    values = {"smtp_host": "smtp.example.com", "smtp_port": 587, "smtp_username": "sos@example.com",
              "smtp_password": SecretStr("app-password"), "smtp_from": "",
              "smtp_security": "starttls"}
    values.update(overrides)
    return get_settings().model_copy(update=values)


def test_not_set_up_fails_without_retrying():
    sender = EmailSender(_settings(smtp_host=""))
    assert not sender.configured()
    with pytest.raises(DeliveryError) as caught:
        sender.send("mom@example.com", "SOS", "help")
    assert caught.value.message == EMAIL_NOT_SET_UP
    assert caught.value.retryable is False
    assert FakeSMTP.instances == []


def test_sends_with_starttls_and_login():
    EmailSender(_settings()).send("mom@example.com", "EMERGENCY SOS: Ana needs help.", "Body text")
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.example.com", 587)
    assert smtp.calls[:2] == ["starttls", ("login", "sos@example.com", "app-password")]
    message = smtp.sent[0]
    assert message["To"] == "mom@example.com"
    assert message["From"] == "sos@example.com"
    assert message["Subject"] == "EMERGENCY SOS: Ana needs help."
    assert "Body text" in message.get_content()


def test_ssl_mode_and_separate_from_address():
    EmailSender(_settings(smtp_security="ssl", smtp_port=465,
                          smtp_from="IrisClick SOS <sos@example.com>")).send("a@b.co", "S", "B")
    smtp = FakeSMTP.instances[0]
    assert "starttls" not in smtp.calls
    assert smtp.sent[0]["From"] == "IrisClick SOS <sos@example.com>"


@pytest.mark.parametrize(("error", "retryable"), [
    (smtplib.SMTPAuthenticationError(535, b"bad"), False),
    (smtplib.SMTPRecipientsRefused({"a@b.co": (550, b"no")}), False),
    (smtplib.SMTPSenderRefused(550, b"no", "sos@example.com"), False),
    (smtplib.SMTPServerDisconnected("gone"), True),
    (ConnectionRefusedError("offline"), True),
    (TimeoutError("slow"), True),
])
def test_errors_say_whether_retrying_can_help(error, retryable):
    FakeSMTP.fail_with = error
    with pytest.raises(DeliveryError) as caught:
        EmailSender(_settings()).send("a@b.co", "S", "B")
    assert caught.value.retryable is retryable
    if retryable:
        assert caught.value.message == CANNOT_REACH


def test_sms_is_not_set_up_yet():
    sms = NotConfiguredSms()
    assert not sms.configured()
    with pytest.raises(DeliveryError) as caught:
        sms.send("+639171234567", "S", "B")
    assert caught.value.message == SMS_NOT_SET_UP
    assert caught.value.retryable is False
