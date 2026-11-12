"""The SMS sender (Phase 5): never texts during tests, keeps to SMS_ONLY_TO, never pretends."""

import pytest
import requests

from app.accounts import sms

ME = "+639178082488"


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setenv(sms.KEY_ENV, "test-key-not-real")
    monkeypatch.setenv(sms.ONLY_TO_ENV, "09178082488")
    monkeypatch.setenv(sms.SENDER_ENV, "")


def test_nothing_is_ever_texted_while_tests_run(monkeypatch):
    called = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: called.append(1))
    assert sms.configured() is False  # even with a key set
    with pytest.raises(sms.SmsError) as err:
        sms.send(ME, "hello")
    assert err.value.reason == "not_configured" and called == []


def test_the_testing_lock_allows_only_that_number():
    sent = []
    with sms.fake_sender(lambda number, text: sent.append(number)):
        sms.send("0917 808 2488", "hello")
        with pytest.raises(sms.SmsError) as err:
            sms.send("0917 123 4567", "hello")
    assert sent == [ME] and err.value.reason == "not_allowed"


def test_without_the_lock_anyone_may_be_texted(monkeypatch):
    monkeypatch.setenv(sms.ONLY_TO_ENV, "")
    sent = []
    with sms.fake_sender(lambda number, text: sent.append(number)):
        sms.send("0917 123 4567", "hello")
    assert sent == ["+639171234567"]


class Answer:
    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body
        self.content = b"x"

    def json(self):
        return self._body


def test_semaphore_gets_the_local_number_key_and_text(monkeypatch):
    seen = {}

    def post(url, data, timeout):
        seen.update(url=url, data=data, timeout=timeout)
        return Answer(200, [{"message_id": 1, "status": "Pending"}])

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setenv(sms.SENDER_ENV, "IrisClick")
    sms._semaphore(ME, "hello")  # noqa: SLF001 - the adapter itself
    assert seen["url"] == sms.SEMAPHORE_URL
    assert seen["data"] == {"apikey": "test-key-not-real", "number": "09178082488", "message": "hello",
                            "sendername": "IrisClick"}


@pytest.mark.parametrize("answer", [Answer(401, {"apikey": ["invalid"]}), Answer(200, []),
                                    Answer(200, [{"status": "Failed"}]), Answer(402, ["no credits"])])
def test_semaphore_refusals_are_failures_not_sent(monkeypatch, answer):
    monkeypatch.setattr(requests, "post", lambda *a, **k: answer)
    with pytest.raises(sms.SmsError) as err:
        sms._semaphore(ME, "hello")  # noqa: SLF001
    assert err.value.reason == "failed"


def test_a_network_error_is_a_failure(monkeypatch):
    def post(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(sms.SmsError):
        sms._semaphore(ME, "hello")  # noqa: SLF001
