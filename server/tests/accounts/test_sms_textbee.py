"""TextBee: texts go out from the owner's own Android phone (TextBee app). No real request is sent."""

import pytest
import requests

from app.accounts import sms


class Answer:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.content = b"x" if body is not None else b""

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def textbee(monkeypatch):
    monkeypatch.setenv(sms.PROVIDER_ENV, "")
    monkeypatch.setenv(sms.TEXTBEE_KEY_ENV, "tb-test-key-not-real")
    monkeypatch.setenv(sms.TEXTBEE_DEVICE_ENV, "")
    monkeypatch.setenv(sms.KEY_ENV, "")
    monkeypatch.setenv(sms.ONLY_TO_ENV, "09178082488")


@pytest.fixture
def posted(monkeypatch):
    calls = []

    def answer_with(status=201, body=None):
        body = {"data": {"success": True, "smsBatchId": "b1", "recipientCount": 1}} if body is None else body

        def post(url, **kwargs):
            calls.append((url, kwargs))
            return Answer(status, body)
        monkeypatch.setattr(requests, "post", post)
        return calls
    return answer_with


def test_textbee_is_chosen_when_its_key_is_set(monkeypatch):
    assert sms.provider() == sms.TEXTBEE and sms.provider_name() == "TextBee"
    monkeypatch.setenv(sms.PROVIDER_ENV, "semaphore")
    assert sms.provider() == sms.SEMAPHORE
    monkeypatch.setenv(sms.PROVIDER_ENV, "")
    monkeypatch.setenv(sms.TEXTBEE_KEY_ENV, "")
    assert sms.provider() == sms.SEMAPHORE  # no TextBee key: Semaphore, as before


def test_the_request_matches_textbee_docs(posted):
    calls = posted()
    sms._textbee("+639178082488", "Your IrisClick code is 123456.")
    url, kwargs = calls[0]
    assert url == "https://api.textbee.dev/api/v1/gateway/send-sms"
    assert kwargs["headers"] == {"x-api-key": "tb-test-key-not-real"}
    assert kwargs["json"] == {"recipients": ["+639178082488"], "message": "Your IrisClick code is 123456."}
    assert kwargs["timeout"] == sms.TIMEOUT_S


def test_a_chosen_phone_is_sent_as_device_id(posted, monkeypatch):
    monkeypatch.setenv(sms.TEXTBEE_DEVICE_ENV, "phone-123")
    calls = posted()
    sms._textbee("+639178082488", "hi")
    assert calls[0][1]["json"]["deviceId"] == "phone-123"


@pytest.mark.parametrize(("status", "body", "reason"), [
    (429, {"error": "daily limit"}, "limit_reached"),
    (400, {"error": "no enabled device"}, "no_phone"),
    (401, {"error": "invalid api key"}, "failed"),
    (201, {"data": {"success": False}}, "failed"),
    (201, {"data": {"success": True, "successCount": 0, "failureCount": 1}}, "failed"),
])
def test_refusals_are_never_reported_as_sent(posted, status, body, reason):
    posted(status, body)
    with pytest.raises(sms.SmsError) as refused:
        sms._textbee("+639178082488", "hi")
    assert refused.value.reason == reason


def test_a_network_error_is_a_failure(monkeypatch):
    def broken(*a, **k):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(requests, "post", broken)
    with pytest.raises(sms.SmsError) as refused:
        sms._textbee("+639178082488", "hi")
    assert refused.value.reason == "failed"


def test_the_testing_lock_and_the_test_guard_still_apply(posted):
    calls = posted()
    with pytest.raises(sms.SmsError) as refused:
        sms.send("09170000000", "hi")  # not the SMS_ONLY_TO number
    assert refused.value.reason == "not_allowed"
    with pytest.raises(sms.SmsError) as refused:
        sms.send("09178082488", "hi")  # allowed number, but nothing is texted while tests run
    assert refused.value.reason == "not_configured"
    assert calls == []


def test_send_uses_textbee(monkeypatch):
    sent = []
    monkeypatch.setattr(sms, "_under_tests", lambda: False)
    monkeypatch.setattr(sms, "_textbee", lambda n, t: sent.append(("textbee", n)))
    monkeypatch.setattr(sms, "_semaphore", lambda n, t: sent.append(("semaphore", n)))
    sms.send("09178082488", "hi")
    assert sent == [("textbee", "+639178082488")]
