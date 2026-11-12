"""'I'm new' asks about the daily limit before calibrating, so nobody calibrates only to be refused."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.accounts import devices, mode, service
from app.api.routes import accounts

PC = "C" * 43
PIN = "482913"


def on():
    return {devices.DEVICE_HEADER: PC}


@pytest.fixture
def api(monkeypatch, test_database):
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    app = FastAPI()
    app.include_router(accounts.router, prefix="/api")
    return TestClient(app)


def test_a_new_computer_may_make_accounts(api):
    assert api.get("/api/accounts/can-sign-up", headers=on()).json() == {"allowed": True}


def test_after_the_daily_limit_it_says_so_before_calibrating(api, monkeypatch, test_database):
    with test_database() as db:
        devices.remember_device(db, PC)  # the computer is known
    monkeypatch.setattr(service.limits, "signup_allowed", lambda *a, **k: False)
    body = api.get("/api/accounts/can-sign-up", headers=on()).json()
    assert body == {"allowed": False, "detail": service.MESSAGES["signup_limit"]}


def test_sign_up_and_the_question_use_the_same_limit(api, monkeypatch):
    monkeypatch.setattr(service.limits, "signup_allowed", lambda *a, **k: False)
    made = api.post("/api/accounts/signup", headers=on(), json={
        "consent": True, "username": "mari_lapu", "mobile_number": "0917 808 2488", "pin": PIN, "pin_confirm": PIN})
    assert made.status_code == 429 and made.json()["code"] == "signup_limit"
