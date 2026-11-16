"""Semaphore refuses every text until the account has a sender name (found in the live test, 13 Nov 2026).

The admin's Test SMS must say so instead of "check the API key and the credits". Nothing is sent here:
Semaphore's reply is faked.
"""

import json

import pytest

from app.accounts import sms


class FakeReply:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.content = json.dumps(body).encode()
        self._body = body

    def json(self):
        return self._body


def fake_post(reply):
    def post(url, data=None, timeout=None):
        return reply
    return post


def test_a_missing_sender_name_has_its_own_reason(monkeypatch):
    body = [{"senderName": "No active sender name found. Please apply for a sender name before sending messages."}]
    monkeypatch.setattr(sms.requests, "post", fake_post(FakeReply(500, body)))
    with pytest.raises(sms.SmsError) as caught:
        sms._semaphore("+639178082488", "test")
    assert caught.value.reason == "no_sender_name"


@pytest.mark.parametrize("status, body", [
    (500, [{"apikey": "The selected apikey is invalid."}]),
    (200, [{"message_id": 1, "status": "Failed"}]),
    (500, None),
])
def test_other_refusals_stay_failed(monkeypatch, status, body):
    monkeypatch.setattr(sms.requests, "post", fake_post(FakeReply(status, body)))
    with pytest.raises(sms.SmsError) as caught:
        sms._semaphore("+639178082488", "test")
    assert caught.value.reason == "failed"
