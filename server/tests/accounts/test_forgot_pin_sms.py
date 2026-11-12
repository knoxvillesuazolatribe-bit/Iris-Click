"""Phase 5 end to end with a fake sender: verify the mobile number, Forgot PIN by text, limits."""

import re
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.accounts import devices, mode, sms, sms_codes
from app.api.routes import accounts
from app.models.account_models import UserAccount
from app.models.sms_models import SmsCode
from app.models.system_log import SystemLog
from app.models.timestamps import utc_now
from app.models.user_session import UserSession
from app.services import active_user

PC = "S" * 43
PIN, NEW_PIN = "482913", "730591"
MARI = {"consent": True, "username": "mari_lapu", "mobile_number": "0917 808 2488", "pin": PIN, "pin_confirm": PIN}


def on():
    return {devices.DEVICE_HEADER: PC}


@pytest.fixture(autouse=True)
def own_file(tmp_path, monkeypatch):
    active_user.use_path(tmp_path / "active_user.json")
    monkeypatch.setenv(sms.ONLY_TO_ENV, "09178082488")
    yield
    active_user.set_user_id(None)


@pytest.fixture
def texts():
    sent = []
    with sms.fake_sender(lambda number, text: sent.append((number, text))):
        yield sent


@pytest.fixture
def api(monkeypatch, test_database):
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    app = FastAPI()
    app.include_router(accounts.mode_router, prefix="/api")
    app.include_router(accounts.router, prefix="/api")
    return TestClient(app)


def code_in(texts):
    return re.search(r"\b(\d{6})\b", texts[-1][1]).group(1)


def back_in_time(test_database, seconds=61):
    with test_database() as db:
        for row in db.scalars(select(SmsCode)).all():
            row.created_at = row.created_at - timedelta(seconds=seconds)
        db.commit()


def verified_mari(api, texts):
    assert api.post("/api/accounts/mobile/send", json={"mobile_number": "0917 808 2488"}, headers=on()).json() == {
        "to": "09** *** 2488", "resend_after": 60}
    ticket = api.post("/api/accounts/mobile/verify", json={"mobile_number": "09178082488", "code": code_in(texts)},
                      headers=on()).json()["ticket"]
    made = api.post("/api/accounts/signup", json=MARI, headers=on())
    assert api.post("/api/accounts/mobile/confirm", json={"mobile_ticket": ticket}, headers=on()).status_code == 204
    return made.json()["user_id"]


def test_mode_says_whether_sms_works(api, texts):
    assert api.get("/api/signin/mode").json()["sms_enabled"] is True


def test_without_sms_the_number_is_saved_unverified(api):
    sent = api.post("/api/accounts/mobile/send", json={"mobile_number": "0917 808 2488"}, headers=on())
    assert sent.status_code == 503 and sent.json()["code"] == "sms_off"


def test_verify_the_mobile_number_at_sign_up(api, texts, test_database):
    uid = verified_mari(api, texts)
    assert texts[0][0] == "+639178082488" and "IrisClick" in texts[0][1]
    with test_database() as db:
        assert db.get(UserAccount, uid).mobile_verified_at is not None
        logs = db.scalars(select(SystemLog)).all()
        assert any(log.activity_type == "mobile_verified" for log in logs)
        assert all(code_in(texts) not in (log.activity_description or "") for log in logs)
        assert all("8082488" not in (log.activity_description or "") for log in logs)


def test_a_ticket_for_another_number_does_not_verify(api, texts, monkeypatch):
    monkeypatch.setenv(sms.ONLY_TO_ENV, "")
    api.post("/api/accounts/mobile/send", json={"mobile_number": "0917 123 4567"}, headers=on())
    ticket = api.post("/api/accounts/mobile/verify", json={"mobile_number": "09171234567", "code": code_in(texts)},
                      headers=on()).json()["ticket"]
    api.post("/api/accounts/signup", json=MARI, headers=on())
    assert api.post("/api/accounts/mobile/confirm", json={"mobile_ticket": ticket}, headers=on()).status_code == 409


def test_wrong_codes_count_down_and_codes_expire(api, texts, test_database):
    api.post("/api/accounts/mobile/send", json={"mobile_number": "0917 808 2488"}, headers=on())
    for left in (4, 3, 2, 1):
        wrong = api.post("/api/accounts/mobile/verify", json={"mobile_number": "09178082488", "code": "000000"},
                         headers=on())
        assert wrong.status_code == 401 and wrong.json()["tries_left"] == left
    last = api.post("/api/accounts/mobile/verify", json={"mobile_number": "09178082488", "code": "000000"}, headers=on())
    assert last.json()["code"] == "too_many_tries"
    right_but_late = api.post("/api/accounts/mobile/verify", json={"mobile_number": "09178082488",
                                                                   "code": code_in(texts)}, headers=on())
    assert right_but_late.status_code == 429
    back_in_time(test_database)
    api.post("/api/accounts/mobile/send", json={"mobile_number": "0917 808 2488"}, headers=on())
    with test_database() as db:
        newest = db.scalars(select(SmsCode).order_by(SmsCode.code_id.desc())).first()
        newest.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    expired = api.post("/api/accounts/mobile/verify", json={"mobile_number": "09178082488", "code": code_in(texts)},
                       headers=on())
    assert expired.json()["code"] == "no_code"


def test_resend_waits_60_seconds_and_3_texts_an_hour(api, texts, test_database):
    body = {"mobile_number": "0917 808 2488"}
    assert api.post("/api/accounts/mobile/send", json=body, headers=on()).status_code == 200
    again = api.post("/api/accounts/mobile/send", json=body, headers=on())
    assert again.status_code == 429 and again.json()["code"] == "resend_wait" and 0 < again.json()["wait_seconds"] <= 61
    for _ in range(2):
        back_in_time(test_database)
        assert api.post("/api/accounts/mobile/send", json=body, headers=on()).status_code == 200
    back_in_time(test_database)
    assert api.post("/api/accounts/mobile/send", json=body, headers=on()).json()["code"] == "sms_limit"
    assert len(texts) == 3


def test_a_failed_text_saves_nothing_and_says_so(api, test_database):
    def broken(number, text):
        raise sms.SmsError("failed")

    with sms.fake_sender(broken):
        sent = api.post("/api/accounts/mobile/send", json={"mobile_number": "0917 808 2488"}, headers=on())
    assert sent.status_code == 503 and sent.json()["code"] == "cant_send"
    with test_database() as db:
        assert db.scalars(select(SmsCode)).all() == []


def test_forgot_pin_by_text_sets_a_new_pin_and_ends_other_sessions(api, texts, test_database):
    uid = verified_mari(api, texts)
    back_in_time(test_database)
    sent = api.post("/api/accounts/forgot-pin/send", json={"user_id": uid}, headers=on())
    assert sent.json() == {"to": "09** *** 2488", "resend_after": 60}
    ticket = api.post("/api/accounts/forgot-pin/verify", json={"user_id": uid, "code": code_in(texts)},
                      headers=on()).json()["ticket"]
    easy = api.post("/api/accounts/forgot-pin/complete", json={"ticket": ticket, "pin": "123456", "pin_confirm": "123456"},
                    headers=on())
    assert easy.status_code == 422
    done = api.post("/api/accounts/forgot-pin/complete",
                    json={"ticket": ticket, "pin": NEW_PIN, "pin_confirm": NEW_PIN}, headers=on())
    assert done.status_code == 200 and done.json()["username"] == "mari_lapu"
    with test_database() as db:
        sessions = db.scalars(select(UserSession)).all()
        assert sum(1 for s in sessions if s.revoked_at is None) == 1  # only the new one
        kinds = {log.activity_type for log in db.scalars(select(SystemLog))}
        assert {"pin_reset_sms_sent", "pin_reset_by_sms"} <= kinds
    fresh = TestClient(api.app)
    assert fresh.post("/api/accounts/signin", json={"username": "mari_lapu", "pin": NEW_PIN},
                      headers=on()).status_code == 200
    assert fresh.post("/api/accounts/signin", json={"username": "mari_lapu", "pin": PIN},
                      headers=on()).status_code == 401


def test_forgot_pin_needs_a_verified_number(api, texts):
    uid = api.post("/api/accounts/signup", json=MARI, headers=on()).json()["user_id"]
    refused = api.post("/api/accounts/forgot-pin/send", json={"user_id": uid}, headers=on())
    assert refused.status_code == 409 and refused.json()["detail"] == sms_codes.CANT_SEND
    assert texts == []


def test_forgot_pin_only_for_an_account_on_this_computer(api, texts):
    uid = verified_mari(api, texts)
    other = api.post("/api/accounts/forgot-pin/send", json={"user_id": uid}, headers={devices.DEVICE_HEADER: "Z" * 43})
    assert other.status_code in (400, 404)
