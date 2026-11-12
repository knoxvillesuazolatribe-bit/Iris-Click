"""/api/signin/mode and /api/accounts/*: sign-up, sign-in, remove, sign-out."""

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.accounts import devices, mode, service
from app.api.routes import accounts
from app.models.account_models import Device, DeviceAccount, PinAttempt, UserAccount
from app.models.system_log import SystemLog
from app.models.timestamps import utc_now
from app.models.user import User
from app.models.user_session import UserSession
from app.services import session_service

PC1, PC2 = "A" * 43, "B" * 43
PIN = "482913"
MARI = {"consent": True, "username": "mari_lapu", "mobile_number": "0917 808 2488", "pin": PIN, "pin_confirm": PIN}


def on(computer):
    return {devices.DEVICE_HEADER: computer}


def new_client():
    app = FastAPI()
    app.include_router(accounts.mode_router, prefix="/api")
    app.include_router(accounts.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    return new_client()


def sign_up(api, computer=PC1, **changes):
    return api.post("/api/accounts/signup", json={**MARI, **changes}, headers=on(computer))


def tiles(api, computer=PC1):
    return api.get("/api/accounts/tiles", headers=on(computer)).json()


# ---------- the switch ----------

def test_the_website_can_always_ask_which_sign_in_to_show(monkeypatch):
    monkeypatch.delenv(mode.ENV_NAME, raising=False)
    monkeypatch.setattr(mode, "signin_mode", lambda env_file=None: "legacy")
    assert new_client().get("/api/signin/mode").json() == {"mode": "legacy", "sms_enabled": False}


def test_in_legacy_mode_every_account_route_is_closed(monkeypatch, test_database):
    monkeypatch.setenv(mode.ENV_NAME, "legacy")
    client = new_client()
    assert client.get("/api/signin/mode").json()["mode"] == "legacy"
    assert client.get("/api/accounts/tiles", headers=on(PC1)).status_code == 403
    for path in ("signup", "signin", "remove", "signout", "username-check"):
        assert client.post(f"/api/accounts/{path}", json=MARI, headers=on(PC1)).status_code == 403
    with test_database() as db:
        assert db.scalars(select(User)).all() == [] and db.scalars(select(Device)).all() == []


def test_when_turned_on_the_mode_route_says_so(api):
    assert api.get("/api/signin/mode").json()["mode"] == "device_accounts"


# ---------- tiles ----------

def test_a_new_computer_has_no_accounts_and_looking_adds_nothing(api, test_database):
    assert tiles(api) == {"is_shared": False, "accounts": []}
    assert api.get("/api/accounts/tiles").json() == {"is_shared": False, "accounts": []}  # no header at all
    with test_database() as db:
        assert db.scalars(select(Device)).all() == []


# ---------- sign-up ----------

def test_sign_up_creates_the_account_signs_in_and_shows_a_tile(api, test_database):
    response = sign_up(api)
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "mari_lapu" and body["full_name"] == "mari_lapu" and body["role"] == "assistive_user"
    assert tiles(api)["accounts"] == [{"user_id": body["user_id"], "username": "mari_lapu", "needs_pin": True}]
    assert tiles(api, PC2)["accounts"] == []  # only on the computer it was made on
    with test_database() as db:
        account = db.get(UserAccount, body["user_id"])
        assert account.pin_hash.startswith("$argon2id$") and account.mobile_number == "+639178082488"
        assert account.consent_at is not None and account.signup_source == "self" and account.mobile_verified_at is None
        assert db.scalars(select(Device)).one().device_key_hash == devices.device_key_hash(PC1)
        token = api.cookies.get(session_service.COOKIE_NAME)
        assert session_service.resolve(db, token).user.user_id == body["user_id"]


def test_nothing_secret_is_returned_or_logged(api, test_database):
    response = sign_up(api)
    assert all(secret not in response.text for secret in (PIN, "argon2", "9178082488", "8082488"))
    with test_database() as db:
        logs = db.scalars(select(SystemLog)).all()
        assert {log.activity_type for log in logs} >= {"account_created", "consent_given", "pin_created",
                                                       "account_added_to_device"}
        text = " ".join(f"{log.activity_type} {log.activity_description}" for log in logs)
        assert all(secret not in text for secret in (PIN, "argon2", "9178082488", "8082488", PC1))


@pytest.mark.parametrize("changes, status, code", [
    ({"consent": False}, 400, "consent_required"),
    ({"username": "ab"}, 422, "too_short"),
    ({"username": "mari lapu"}, 422, "bad_characters"),
    ({"username": "admin"}, 422, "reserved"),
    ({"mobile_number": "12345"}, 422, "bad_mobile"),
    ({"pin": "123456", "pin_confirm": "123456"}, 422, "too_easy"),
    ({"pin": "082488", "pin_confirm": "082488"}, 422, "too_easy"),  # the end of the mobile number
    ({"pin": "48291", "pin_confirm": "48291"}, 422, "not_six_digits"),
    ({"pin_confirm": "482914"}, 422, "pin_mismatch"),
])
def test_sign_up_refusals_leave_nothing_behind(api, test_database, changes, status, code):
    response = sign_up(api, **changes)
    assert (response.status_code, response.json()["code"]) == (status, code) and response.json()["detail"]
    assert session_service.COOKIE_NAME not in api.cookies
    with test_database() as db:
        assert db.scalars(select(User)).all() == [] and db.scalars(select(UserAccount)).all() == []


def test_sign_up_needs_irisclick_desktop(api, test_database):
    for headers in ({}, {devices.DEVICE_HEADER: "short"}, {devices.DEVICE_HEADER: "x" * 300}):
        response = api.post("/api/accounts/signup", json=MARI, headers=headers)
        assert (response.status_code, response.json()["code"]) == (400, "device_required")
    with test_database() as db:
        assert db.scalars(select(User)).all() == [] and db.scalars(select(Device)).all() == []


def test_a_taken_username_comes_back_with_suggestions(api):
    sign_up(api)
    again = sign_up(new_client(), PC2, username="MARI_LAPU", mobile_number="09171234567")
    assert (again.status_code, again.json()["code"]) == (409, "taken")
    assert len(again.json()["suggestions"]) == 3
    check = api.post("/api/accounts/username-check", json={"username": "Mari_Lapu"}, headers=on(PC1)).json()
    assert check["available"] is False and check["problem"] == "taken" and len(check["suggestions"]) == 3
    assert api.post("/api/accounts/username-check", json={"username": "mia"}, headers=on(PC1)).json() == {
        "available": True, "problem": None, "message": None, "suggestions": []}


def test_five_new_accounts_a_day_per_computer_and_three_per_mobile(api):
    for i in range(3):
        assert sign_up(new_client(), username=f"user{i}").status_code == 201
    fourth = sign_up(new_client(), username="user3")
    assert (fourth.status_code, fourth.json()["code"]) == (409, "mobile_limit")
    for i in (3, 4):
        assert sign_up(new_client(), username=f"user{i}", mobile_number="09171234567").status_code == 201
    sixth = sign_up(new_client(), username="user5", mobile_number="09171234567")
    assert (sixth.status_code, sixth.json()["code"]) == (429, "signup_limit")
    assert sign_up(new_client(), PC2, username="user5", mobile_number="09171234567").status_code == 201


# ---------- sign-in ----------

def signin(api, computer=PC1, **body):
    return api.post("/api/accounts/signin", json=body, headers=on(computer))


def test_a_tile_asks_for_the_pin_and_the_right_pin_signs_in(api):
    uid = sign_up(api).json()["user_id"]
    fresh = new_client()
    needs = signin(fresh, user_id=uid)
    assert (needs.status_code, needs.json()["code"]) == (401, "pin_required")
    ok = signin(fresh, user_id=uid, pin=PIN)
    assert ok.status_code == 200 and ok.json()["username"] == "mari_lapu"
    assert session_service.COOKIE_NAME in fresh.cookies


def test_remember_me_skips_the_pin_until_thirty_days_without_use(api, test_database):
    uid = sign_up(api).json()["user_id"]
    assert signin(new_client(), user_id=uid, pin=PIN, remember=True).status_code == 200
    assert tiles(api)["accounts"][0]["needs_pin"] is False
    assert signin(new_client(), user_id=uid).status_code == 200  # no PIN
    with test_database() as db:
        device = db.scalars(select(Device)).one()
        soon, late = utc_now() + timedelta(days=29), utc_now() + timedelta(days=31)
        assert service.list_tiles(db, device, now=soon)[0].needs_pin is False
        assert service.list_tiles(db, device, now=late)[0].needs_pin is True
        with pytest.raises(service.AccountError) as refused:
            service.sign_in(db, device, user_id=uid, now=late)
        assert refused.value.code == "pin_required"


def test_wrong_pins_count_down_then_wait_then_need_a_reset(api, test_database):
    uid = sign_up(api).json()["user_id"]
    for left in (4, 3, 2, 1):
        wrong = signin(api, user_id=uid, pin="000001")
        assert (wrong.status_code, wrong.json()["code"], wrong.json()["tries_left"]) == (401, "wrong_pin", left)
    fifth = signin(api, user_id=uid, pin="000001")
    assert (fifth.status_code, fifth.json()["code"]) == (429, "wait") and 290 <= fifth.json()["wait_seconds"] <= 301
    locked = signin(api, user_id=uid, pin=PIN)  # even the right PIN waits
    assert (locked.status_code, locked.json()["code"]) == (429, "wait")
    with test_database() as db:
        device = db.scalars(select(Device)).one()
        later = utc_now() + timedelta(minutes=6)
        for _ in range(5):
            with pytest.raises(service.AccountError):
                service.sign_in(db, device, user_id=uid, pin="000001", now=later)
        with pytest.raises(service.AccountError) as refused:
            service.sign_in(db, device, user_id=uid, pin=PIN, now=later + timedelta(days=2))
        assert (refused.value.status_code, refused.value.code) == (423, "reset_needed")
        kinds = {log.activity_type for log in db.scalars(select(SystemLog)).all()}
        assert {"pin_failed", "pin_locked"} <= kinds
    assert signin(new_client(), PC2, username="mari_lapu", pin=PIN).status_code == 200  # another computer still works


def test_a_right_pin_clears_the_wrong_tries(api, test_database):
    uid = sign_up(api).json()["user_id"]
    for _ in range(3):
        signin(api, user_id=uid, pin="000001")
    assert signin(api, user_id=uid, pin=PIN).status_code == 200
    assert signin(api, user_id=uid, pin="000001").json()["tries_left"] == 4
    with test_database() as db:
        assert len(db.scalars(select(PinAttempt)).all()) == 1


def test_i_already_have_an_account_adds_it_to_a_second_computer(api):
    uid = sign_up(api).json()["user_id"]
    other = new_client()
    assert tiles(other, PC2)["accounts"] == []
    ok = signin(other, PC2, username="Mari_Lapu", pin=PIN)
    assert ok.status_code == 200 and ok.json()["user_id"] == uid
    assert [t["username"] for t in tiles(other, PC2)["accounts"]] == ["mari_lapu"]
    assert [t["username"] for t in tiles(api, PC1)["accounts"]] == ["mari_lapu"]


def test_a_wrong_username_and_a_wrong_pin_look_the_same(api):
    sign_up(api)
    other = new_client()
    unknown = signin(other, PC2, username="nobody_here", pin=PIN)
    wrong = signin(other, PC2, username="mari_lapu", pin="000001")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json() == {"detail": "Username or PIN is incorrect.", "code": "wrong_pin"}
    assert signin(other, PC2, username="mari_lapu").json() == unknown.json()  # no PIN sent


def test_sign_in_needs_one_of_tile_or_username_and_a_known_tile(api):
    uid = sign_up(api).json()["user_id"]
    assert signin(api).status_code == 422 and signin(api, user_id=uid, username="mari_lapu").status_code == 422
    missing = signin(api, user_id=uid + 99, pin=PIN)
    assert (missing.status_code, missing.json()["code"]) == (404, "not_on_this_computer")
    elsewhere = signin(new_client(), PC2, user_id=uid, pin=PIN)  # a tile that is not on that computer
    assert (elsewhere.status_code, elsewhere.json()["code"]) == (404, "not_on_this_computer")


def test_a_deactivated_person_has_no_tile_and_cannot_sign_in(api, test_database):
    uid = sign_up(api).json()["user_id"]
    with test_database() as db:
        db.get(User, uid).status = "inactive"
        db.commit()
    assert tiles(api)["accounts"] == []
    assert signin(new_client(), user_id=uid, pin=PIN).status_code == 404
    refused = signin(new_client(), PC2, username="mari_lapu", pin=PIN)
    assert (refused.status_code, refused.json()["code"]) == (401, "wrong_pin")


# ---------- remove and sign out ----------

def test_remove_forgets_the_account_on_this_computer_only(api, test_database):
    uid = sign_up(api).json()["user_id"]
    signin(new_client(), PC2, username="mari_lapu", pin=PIN)
    assert api.post("/api/accounts/remove", json={"user_id": uid}, headers=on(PC1)).status_code == 204
    assert tiles(api, PC1)["accounts"] == [] and len(tiles(api, PC2)["accounts"]) == 1
    again = api.post("/api/accounts/remove", json={"user_id": uid}, headers=on(PC1))
    assert (again.status_code, again.json()["code"]) == (404, "not_on_this_computer")
    with test_database() as db:
        assert db.get(UserAccount, uid) is not None  # the account itself stays
    assert signin(new_client(), PC1, username="mari_lapu", pin=PIN).status_code == 200  # and can be added back
    assert len(tiles(api, PC1)["accounts"]) == 1


def test_a_shared_computer_never_remembers_and_asks_for_the_pin_to_remove(api, test_database):
    uid = sign_up(api, remember=True).json()["user_id"]
    with test_database() as db:
        db.scalars(select(Device)).one().is_shared = True
        db.commit()
    assert tiles(api) == {"is_shared": True, "accounts": [{"user_id": uid, "username": "mari_lapu", "needs_pin": True}]}
    assert signin(new_client(), user_id=uid).json()["code"] == "pin_required"
    assert signin(new_client(), user_id=uid, pin=PIN, remember=True).status_code == 200
    assert tiles(api)["accounts"][0]["needs_pin"] is True
    no_pin = api.post("/api/accounts/remove", json={"user_id": uid}, headers=on(PC1))
    assert (no_pin.status_code, no_pin.json()["code"]) == (401, "pin_required")
    wrong = api.post("/api/accounts/remove", json={"user_id": uid, "pin": "000001"}, headers=on(PC1))
    assert (wrong.status_code, wrong.json()["code"]) == (401, "wrong_pin")
    assert api.post("/api/accounts/remove", json={"user_id": uid, "pin": PIN}, headers=on(PC1)).status_code == 204
    assert tiles(api)["accounts"] == []


def test_sign_out_ends_the_session_and_asks_for_the_pin_next_time(api, test_database):
    uid = sign_up(api, remember=True).json()["user_id"]
    assert tiles(api)["accounts"][0]["needs_pin"] is False
    token = api.cookies.get(session_service.COOKIE_NAME)
    assert api.post("/api/accounts/signout", headers=on(PC1)).status_code == 204
    assert tiles(api)["accounts"][0]["needs_pin"] is True
    with test_database() as db:
        assert session_service.resolve(db, token) is None
        assert db.scalars(select(UserSession)).one().revoked_at is not None
        assert db.scalars(select(DeviceAccount)).one().remembered is False
    assert api.post("/api/accounts/signout", headers=on(PC1)).status_code == 204  # twice is fine
    assert signin(new_client(), user_id=uid).json()["code"] == "pin_required"
