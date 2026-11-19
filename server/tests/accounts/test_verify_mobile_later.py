"""Accounts made while SMS was off: the signed-in person verifies the number already on the account,
and then Forgot PIN can text them. All texts go to a fake sender."""

import pytest

from app.accounts import sms
from tests.accounts.test_forgot_pin_sms import (MARI, api, back_in_time, code_in, on, own_file,  # noqa: F401
                                                signing_secret, texts)


@pytest.fixture
def unverified_mari(api):  # noqa: F811
    """Signed up without a code (as while SMS was off): the number is saved, not verified."""
    made = api.post("/api/accounts/signup", json=MARI, headers=on())
    assert made.status_code == 201
    return made.json()["user_id"]


def test_my_number_shows_masked_and_unverified(api, unverified_mari, texts):  # noqa: F811
    assert api.get("/api/accounts/me/mobile").json() == {"to": "09** *** 2488", "verified": False,
                                                          "sms_enabled": True}


def test_verify_my_number_then_forgot_pin_works(api, unverified_mari, texts, test_database):  # noqa: F811
    refused = api.post("/api/accounts/forgot-pin/send", json={"user_id": unverified_mari}, headers=on())
    assert refused.status_code == 409 and refused.json()["code"] == "not_verified"  # before: refused
    assert len(texts) == 0

    sent = api.post("/api/accounts/me/mobile/send")
    assert sent.json() == {"to": "09** *** 2488", "resend_after": 60}
    assert texts[-1][0] == "+639178082488"  # the number on the account, nobody chooses another
    assert api.post("/api/accounts/me/mobile/verify", json={"code": code_in(texts)}).status_code == 204
    assert api.get("/api/accounts/me/mobile").json()["verified"] is True

    back_in_time(test_database)
    allowed = api.post("/api/accounts/forgot-pin/send", json={"user_id": unverified_mari}, headers=on())
    assert allowed.status_code == 200  # after: Forgot PIN texts a code


def test_a_wrong_code_does_not_verify(api, unverified_mari, texts):  # noqa: F811
    api.post("/api/accounts/me/mobile/send")
    wrong = "000000" if code_in(texts) != "000000" else "111111"
    answer = api.post("/api/accounts/me/mobile/verify", json={"code": wrong})
    assert answer.status_code == 401 and answer.json()["code"] == "wrong_code"
    assert api.get("/api/accounts/me/mobile").json()["verified"] is False


def test_an_already_verified_number_is_not_texted_again(api, unverified_mari, texts):  # noqa: F811
    api.post("/api/accounts/me/mobile/send")
    api.post("/api/accounts/me/mobile/verify", json={"code": code_in(texts)})
    again = api.post("/api/accounts/me/mobile/send")
    assert again.status_code == 409 and again.json()["code"] == "already_verified" and len(texts) == 1


def test_signed_out_people_cannot_use_it(api, texts):  # noqa: F811
    assert api.get("/api/accounts/me/mobile").status_code in (401, 403)
    assert api.post("/api/accounts/me/mobile/send").status_code in (401, 403)
    assert texts == []


def test_without_sms_it_says_so(api, unverified_mari):  # noqa: F811
    assert api.get("/api/accounts/me/mobile").json()["sms_enabled"] is False  # tests never text for real
    answer = api.post("/api/accounts/me/mobile/send")
    assert answer.status_code == 503 and answer.json()["code"] == "sms_off"
    assert sms.configured() is False
