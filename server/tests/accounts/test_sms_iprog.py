"""iProg SMS: a Philippine gateway (no phone needed). No real request is sent."""

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
def iprog(monkeypatch):
    monkeypatch.setenv(sms.PROVIDER_ENV, "")
    monkeypatch.setenv(sms.IPROG_TOKEN_ENV, "iprog-test-token-not-real")
    monkeypatch.setenv(sms.KEY_ENV, "")
    monkeypatch.setenv(sms.ONLY_TO_ENV, "09178082488")


@pytest.fixture
def posted(monkeypatch):
    calls = []

    def answer_with(status=200, body=None):
        body = ({"status": 200, "message": "Your SMS message has been successfully added to the queue.",
                 "message_id": "iSms-XHYBk"} if body is None else body)

        def post(url, **kwargs):
            calls.append((url, kwargs))
            return Answer(status, body)
        monkeypatch.setattr(requests, "post", post)
        return calls
    return answer_with


def test_iprog_is_chosen_when_its_token_is_set(monkeypatch):
    assert sms.provider() == sms.IPROG and sms.provider_name() == "iProg SMS"
    monkeypatch.setenv(sms.KEY_ENV, "old-semaphore-key")
    assert sms.provider() == sms.IPROG  # iProg wins over an old Semaphore key
    monkeypatch.setenv(sms.PROVIDER_ENV, "semaphore")
    assert sms.provider() == sms.SEMAPHORE  # SMS_PROVIDER decides
    monkeypatch.setenv(sms.PROVIDER_ENV, "")
    monkeypatch.setenv(sms.IPROG_TOKEN_ENV, "")
    assert sms.provider() == sms.SEMAPHORE  # no iProg token: Semaphore, as before


def test_the_request_matches_iprog_docs(posted):
    calls = posted()
    sms._iprog("+639178082488", "Your IrisClick code is 123456.")
    url, kwargs = calls[0]
    assert url == "https://www.iprogsms.com/api/v1/sms_messages"
    assert kwargs["json"] == {"api_token": "iprog-test-token-not-real", "phone_number": "639178082488",
                              "message": "Your IrisClick code is 123456."}
    assert "params" not in kwargs  # the token never goes in the URL
    assert kwargs["timeout"] == sms.TIMEOUT_S


@pytest.mark.parametrize(("status", "body"), [
    (200, {"status": 500, "message": "Invalid Token"}),       # iProg's error comes in the body
    (200, {"status": "error", "message": "Invalid phone number format."}),
    (200, {"status": 200, "message": "queued"}),              # no message id: not trusted as sent
    (500, {"status": 500, "message": "Server error"}),
    (200, {}),                                                # empty answer
])
def test_refusals_are_never_reported_as_sent(posted, status, body):
    posted(status, body)
    with pytest.raises(sms.SmsError) as refused:
        sms._iprog("+639178082488", "hi")
    assert refused.value.reason == "failed"


def test_a_network_error_is_a_failure(monkeypatch):
    def broken(*a, **k):
        raise requests.Timeout("slow")
    monkeypatch.setattr(requests, "post", broken)
    with pytest.raises(sms.SmsError) as refused:
        sms._iprog("+639178082488", "hi")
    assert refused.value.reason == "failed"


def test_send_uses_iprog_and_the_lock_still_applies(monkeypatch):
    sent = []
    monkeypatch.setattr(sms, "_under_tests", lambda: False)
    monkeypatch.setattr(sms, "_iprog", lambda n, t: sent.append(("iprog", n)))
    monkeypatch.setattr(sms, "_semaphore", lambda n, t: sent.append(("semaphore", n)))
    sms.send("09178082488", "hi")
    assert sent == [("iprog", "+639178082488")]
    with pytest.raises(sms.SmsError) as refused:
        sms.send("09170000000", "hi")  # not the SMS_ONLY_TO number
    assert refused.value.reason == "not_allowed" and len(sent) == 1


def test_nothing_is_texted_while_tests_run(posted):
    calls = posted()
    with pytest.raises(sms.SmsError) as refused:
        sms.send("09178082488", "hi")
    assert refused.value.reason == "not_configured" and calls == []
