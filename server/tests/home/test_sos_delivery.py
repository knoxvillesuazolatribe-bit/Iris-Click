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

    def __init__(self, host, port, timeout=None, context=None, local_hostname=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.local_hostname = local_hostname
        self.calls: list = []
        self.sent = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")
        return False

    def ehlo(self, name=""):
        self.calls.append("ehlo")
        return 250, b"smtp.example.com at your service"

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
    calls = [c for c in smtp.calls if c != "ehlo"]
    assert calls[:2] == ["starttls", ("login", "sos@example.com", "app-password")]
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
        assert caught.value.message == f"{CANNOT_REACH} ({type(error).__name__})"


def test_a_connection_failure_names_its_cause_and_is_logged(caplog):
    FakeSMTP.fail_with = smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
    with caplog.at_level("WARNING", logger="irisclick.sos"), pytest.raises(DeliveryError) as caught:
        EmailSender(_settings()).send("a@b.co", "S", "B")
    assert "(SMTPServerDisconnected)" in caught.value.message
    assert "failed at send: SMTPServerDisconnected: Connection unexpectedly closed" in caplog.text
    assert _settings().smtp_password.get_secret_value() not in caplog.text


def test_sms_is_not_set_up_yet():
    sms = NotConfiguredSms()
    assert not sms.configured()
    with pytest.raises(DeliveryError) as caught:
        sms.send("+639171234567", "S", "B")
    assert caught.value.message == SMS_NOT_SET_UP
    assert caught.value.retryable is False


def test_the_log_names_the_step_that_failed(monkeypatch, caplog):
    def hang_up_at_starttls(self, context=None):
        raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

    monkeypatch.setattr(FakeSMTP, "starttls", hang_up_at_starttls)
    with caplog.at_level("WARNING", logger="irisclick.sos"), pytest.raises(DeliveryError):
        EmailSender(_settings()).send("a@b.co", "S", "B")
    assert "failed at tls: SMTPServerDisconnected" in caplog.text


def test_a_connection_that_cannot_open_is_the_connect_step(monkeypatch, caplog):
    def refuse(*args, **kwargs):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(sos_delivery.smtplib, "SMTP", refuse)
    with caplog.at_level("WARNING", logger="irisclick.sos"), pytest.raises(DeliveryError):
        EmailSender(_settings()).send("a@b.co", "S", "B")
    assert "failed at connect: ConnectionRefusedError" in caplog.text


def test_pasted_spaces_and_line_breaks_are_trimmed_before_signing_in():
    EmailSender(_settings(smtp_username=" sos@example.com\n",
                          smtp_password=SecretStr("abcdefghijklmnop\n"))).send("a@b.co", "S", "B")
    assert ("login", "sos@example.com", "abcdefghijklmnop") in FakeSMTP.instances[0].calls


def test_online_the_server_says_hello_by_the_site_name(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    EmailSender(_settings()).send("a@b.co", "S", "B")
    assert FakeSMTP.instances[0].local_hostname == sos_delivery.ONLINE_HELLO_NAME


def test_on_a_pc_smtplib_keeps_its_own_hello_name(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    EmailSender(_settings()).send("a@b.co", "S", "B")
    assert FakeSMTP.instances[0].local_hostname is None


def test_hello_comes_before_tls_and_again_after():
    EmailSender(_settings()).send("a@b.co", "S", "B")
    calls = FakeSMTP.instances[0].calls
    assert calls[:3] == ["ehlo", "starttls", "ehlo"] and calls[3][0] == "login"


def test_the_failure_log_shows_the_password_shape_not_the_password(caplog):
    FakeSMTP.fail_with = smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
    with caplog.at_level("WARNING", logger="irisclick.sos"), pytest.raises(DeliveryError):
        EmailSender(_settings(smtp_password=SecretStr("abcd efgh ijkl mnop\n"))).send("a@b.co", "S", "B")
    assert "hello reply 250" in caplog.text
    assert "password 20 characters, spaces or line breaks at the ends, spaces inside" in caplog.text
    assert "abcd" not in caplog.text


def test_secret_shape():
    assert sos_delivery.secret_shape("abcdefghijklmnop") == "16 characters"
    assert sos_delivery.secret_shape("") == "0 characters"
