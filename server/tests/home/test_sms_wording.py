"""Text wording: each code fits one SMS, and SOS texts are short (the email keeps the full message)."""

from datetime import UTC, datetime

from app.accounts import sms_codes
from app.models.user import User
from app.services import sos_service

ONE_SMS = 160 - len("IrisClick\n")  # iProg adds the account header on the first line
WHEN = datetime(2026, 11, 19, 8, 30, tzinfo=UTC)  # 4:30 PM in the Philippines


def test_each_code_text_fits_one_sms_and_keeps_the_code():
    for template in sms_codes.TEXTS.values():
        text = template.format(code="123456")
        assert "123456" in text and "10 minutes" in text
        assert len(text) <= ONE_SMS
        assert not text.startswith("IrisClick")  # the header already says it


def test_the_sos_text_is_short_and_has_name_place_and_time():
    text = sos_service.build_sms_message(User(full_name="Juan Dela Cruz"), "Pusok, Lapu-Lapu City", WHEN)
    assert text == ("SOS: Juan Dela Cruz needs help now. Location: Pusok, Lapu-Lapu City. "
                    "Time: Nov 19, 4:30 PM. Please call or go to them. - PDAO Lapu-Lapu")
    assert len(text) <= 2 * 153  # at most two joined texts


def test_without_an_address_the_text_asks_them_to_call():
    text = sos_service.build_sms_message(User(full_name="Ana"), None, WHEN)
    assert "Location: unknown, please call them." in text


def test_the_email_keeps_the_full_message():
    email = sos_service.build_message(User(full_name="Ana"), "Pusok, Lapu-Lapu City", WHEN)
    assert email.startswith("EMERGENCY SOS: Ana needs help.") and "Please call them or go to them" in email
