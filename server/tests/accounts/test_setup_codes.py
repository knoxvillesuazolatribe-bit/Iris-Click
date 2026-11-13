"""Setup codes (build step 11): PDAO's 8-digit code to set a PIN or create a first account."""

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.accounts import devices, mode, setup_codes
from app.api.routes import accounts
from app.models.account_models import SetupCode, UserAccount
from app.models.system_log import SystemLog
from app.models.timestamps import utc_now
from app.models.user import User

PC = "Q" * 43
PIN, NEW_PIN = "482913", "907351"


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("IRISCLICK_DESKTOP_SECRET", "s" * 40)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    app = FastAPI()
    app.include_router(accounts.router, prefix="/api")
    return TestClient(app)


def on():
    return {devices.DEVICE_HEADER: PC}


def people(factory):
    with factory() as db:
        admin = User(full_name="PDAO Admin", role="admin", email="admin@pdao.ph", password_hash="$argon2id$fake")
        mari = User(full_name="Mari", role="assistive_user")  # made by the admin before accounts existed
        db.add_all([admin, mari])
        db.commit()
        return admin, mari.user_id


def make_code(factory, admin, user_id, **kw):
    with factory() as db:
        return setup_codes.create_code(db, db.get(User, admin.user_id), user_id, **kw).code


def test_a_code_is_eight_digits_stored_only_as_a_hash(test_database):
    admin, mari = people(test_database)
    code = make_code(test_database, admin, mari)
    assert setup_codes.is_code(code) and setup_codes.show(code) == f"{code[:4]} {code[4:]}"
    with test_database() as db:
        row = db.scalars(select(SetupCode)).one()
        assert row.code_hash.startswith("$argon2id$") and code not in row.code_hash
        assert row.created_by == admin.user_id and row.used_at is None
        assert db.scalars(select(SystemLog.activity_type)).all() == ["pin_reset_by_admin"]
        logged = " ".join(log.activity_description for log in db.scalars(select(SystemLog)).all())
        assert code not in logged


def test_a_new_code_replaces_the_old_one(test_database, api):
    admin, mari = people(test_database)
    old = make_code(test_database, admin, mari)
    new = make_code(test_database, admin, mari)
    assert api.post("/api/accounts/setup-code", json={"code": old}, headers=on()).json()["code"] == "wrong_code"
    assert api.post("/api/accounts/setup-code", json={"code": new}, headers=on()).status_code == 200


def test_a_first_account_from_a_setup_code(test_database, api):
    admin, mari = people(test_database)
    code = make_code(test_database, admin, mari)
    found = api.post("/api/accounts/setup-code", json={"code": setup_codes.show(code)}, headers=on()).json()
    assert found["full_name"] == "Mari" and found["username"] is None and code not in found["ticket"]
    done = api.post("/api/accounts/setup-complete", headers=on(), json={
        "ticket": found["ticket"], "consent": True, "username": "mari_lapu", "mobile_number": "0917 808 2488",
        "pin": PIN, "pin_confirm": PIN})
    assert done.status_code == 200 and done.json()["user_id"] == mari and done.json()["username"] == "mari_lapu"
    with test_database() as db:
        account = db.get(UserAccount, mari)
        assert (account.username, account.mobile_number, account.signup_source) == ("mari_lapu", "+639178082488", "admin")
        assert account.consent_at is not None and db.get(User, mari).full_name == "Mari"  # the admin's name stays
        assert db.scalars(select(SetupCode)).one().used_at is not None
    tiles = api.get("/api/accounts/tiles", headers=on()).json()["accounts"]
    assert [t["username"] for t in tiles] == ["mari_lapu"]
    again = api.post("/api/accounts/setup-complete", headers=on(), json={
        "ticket": found["ticket"], "consent": True, "username": "mari2", "mobile_number": "09178082488",
        "pin": PIN, "pin_confirm": PIN})
    assert again.json()["code"] == "ticket_expired"  # one use


def test_a_forgotten_pin_is_replaced_and_the_old_pin_stops_working(test_database, api):
    admin, mari = people(test_database)
    first = make_code(test_database, admin, mari)
    ticket = api.post("/api/accounts/setup-code", json={"code": first}, headers=on()).json()["ticket"]
    api.post("/api/accounts/setup-complete", headers=on(), json={
        "ticket": ticket, "consent": True, "username": "mari_lapu", "mobile_number": "09178082488",
        "pin": PIN, "pin_confirm": PIN})
    reset = make_code(test_database, admin, mari)
    old_pin = api.post("/api/accounts/signin", json={"username": "mari_lapu", "pin": PIN}, headers=on())
    assert old_pin.status_code == 423 and old_pin.json()["code"] == "reset_needed"
    found = api.post("/api/accounts/setup-code", json={"code": reset}, headers=on()).json()
    assert found["username"] == "mari_lapu"
    done = api.post("/api/accounts/setup-complete", headers=on(), json={
        "ticket": found["ticket"], "pin": NEW_PIN, "pin_confirm": NEW_PIN})
    assert done.status_code == 200
    assert api.post("/api/accounts/signin", json={"username": "mari_lapu", "pin": NEW_PIN}, headers=on()).status_code == 200


@pytest.mark.parametrize("body, code", [
    ({"consent": False, "username": "mari_lapu", "mobile_number": "09178082488", "pin": PIN, "pin_confirm": PIN},
     "consent_required"),
    ({"consent": True, "username": "ab", "mobile_number": "09178082488", "pin": PIN, "pin_confirm": PIN}, "too_short"),
    ({"consent": True, "username": "mari_lapu", "mobile_number": "123", "pin": PIN, "pin_confirm": PIN}, "bad_mobile"),
    ({"consent": True, "username": "mari_lapu", "mobile_number": "09178082488", "pin": "123456",
      "pin_confirm": "123456"}, "too_easy"),
    ({"consent": True, "username": "mari_lapu", "mobile_number": "09178082488", "pin": PIN,
      "pin_confirm": NEW_PIN}, "pin_mismatch"),
])
def test_refusals_keep_the_code_usable(test_database, api, body, code):
    admin, mari = people(test_database)
    ticket = api.post("/api/accounts/setup-code", json={"code": make_code(test_database, admin, mari)},
                      headers=on()).json()["ticket"]
    refused = api.post("/api/accounts/setup-complete", headers=on(), json={"ticket": ticket, **body})
    assert refused.json()["code"] == code
    with test_database() as db:
        assert db.scalars(select(SetupCode)).one().used_at is None and db.get(UserAccount, mari) is None


def test_wrong_and_expired_codes_count_and_then_wait(test_database, api):
    admin, mari = people(test_database)
    expired = make_code(test_database, admin, mari, now=utc_now() - timedelta(hours=25))
    first = api.post("/api/accounts/setup-code", json={"code": expired}, headers=on())
    assert (first.status_code, first.json()["code"], first.json()["tries_left"]) == (401, "wrong_code", 4)
    for _ in range(4):
        api.post("/api/accounts/setup-code", json={"code": "00000000"}, headers=on())
    blocked = api.post("/api/accounts/setup-code", json={"code": "12345678"}, headers=on())
    assert blocked.status_code == 429 and blocked.json()["code"] == "wait" and blocked.json()["wait_seconds"] > 0
    assert api.post("/api/accounts/setup-code", json={"code": "abc"}, headers={}).json()["code"] == "device_required"


def test_a_forged_ticket_is_refused():
    with pytest.raises(setup_codes.SetupCodeError):
        setup_codes.read_ticket("eyJjIjoxLCJ1IjoxLCJlIjo5OTk5OTk5OTk5fQ.forged")
    good = setup_codes.make_ticket(1, 2)
    assert setup_codes.read_ticket(good) == (1, 2)
    with pytest.raises(setup_codes.SetupCodeError):
        setup_codes.read_ticket(good, now=10 ** 12)
