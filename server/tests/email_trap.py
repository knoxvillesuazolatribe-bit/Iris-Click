"""A fixture that records any attempt to send email, so a test can prove none was made."""

import smtplib

import pytest

from app.services import sos_delivery


@pytest.fixture
def email_attempts(monkeypatch):
    attempts = []

    def trap(name):
        def record(*args, **kwargs):
            attempts.append(name)
            raise AssertionError(f"{name} was used: this flow must not send email")
        return record

    monkeypatch.setattr(smtplib, "SMTP", trap("smtplib.SMTP"))
    monkeypatch.setattr(smtplib, "SMTP_SSL", trap("smtplib.SMTP_SSL"))
    monkeypatch.setattr(sos_delivery.EmailSender, "send", trap("EmailSender.send"))
    return attempts
