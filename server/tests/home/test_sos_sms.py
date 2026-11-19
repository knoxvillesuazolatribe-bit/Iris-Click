"""SOS alerts reach SMS contacts through the sign-in code sender (iProg SMS). Nothing is texted."""

import pytest

from app.accounts import sms
from app.services import sos_delivery
from app.services.sos_delivery import SMS_NOT_SET_UP, AccountsSms, DeliveryError
from app.services.sos_dispatcher import SosDispatcher

ALERT = "EMERGENCY SOS: Ana needs help.\n\nLocation: Pusok, Lapu-Lapu City"


def test_the_dispatcher_texts_through_the_accounts_sender():
    assert SosDispatcher().sms_factory is AccountsSms


def test_an_alert_is_texted_to_the_contact(monkeypatch):
    monkeypatch.setenv(sms.ONLY_TO_ENV, "")
    sent = []
    with sms.fake_sender(lambda number, text: sent.append((number, text))):
        assert AccountsSms().configured() is True
        AccountsSms().send("0917 808 2488", "EMERGENCY SOS: Ana needs help.", ALERT)
    assert sent == [("+639178082488", ALERT)]


def test_without_a_sender_it_says_so_and_does_not_retry():
    with pytest.raises(DeliveryError) as caught:
        AccountsSms().send("09178082488", "subject", ALERT)  # tests never text for real
    assert caught.value.message == SMS_NOT_SET_UP and caught.value.retryable is False


@pytest.mark.parametrize(("reason", "retryable"), [
    ("failed", True), ("not_allowed", False), ("no_sender_name", False), ("not_configured", False),
])
def test_refusals_are_explained_and_only_temporary_ones_retried(monkeypatch, reason, retryable):
    def refuse(number, text):
        raise sms.SmsError(reason)
    monkeypatch.setattr(sms, "send", refuse)
    with pytest.raises(DeliveryError) as caught:
        AccountsSms().send("09178082488", "subject", ALERT)
    assert caught.value.retryable is retryable
    assert caught.value.message == sos_delivery.SMS_REFUSED[reason][0]
