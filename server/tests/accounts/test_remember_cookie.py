"""Without "Remember me" the sign-in ends when the browser closes (found in a live test: IrisClick opened
straight on the last person's home although they had not asked to be remembered)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.accounts import devices, mode
from app.api.routes import accounts
from app.services import session_service

PC = "K" * 43
PIN = "482913"
MARI = {"consent": True, "username": "mari_lapu", "mobile_number": "0917 808 2488", "pin": PIN, "pin_confirm": PIN}


def on():
    return {devices.DEVICE_HEADER: PC}


@pytest.fixture
def api(monkeypatch, test_database):
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    app = FastAPI()
    app.include_router(accounts.router, prefix="/api")
    return TestClient(app)


def session_cookie(response):
    [header] = [h for h in response.headers.get_list("set-cookie") if h.startswith(session_service.COOKIE_NAME + "=")]
    return header.lower()


def test_without_remember_me_the_sign_in_ends_with_the_browser(api):
    made = api.post("/api/accounts/signup", json=MARI, headers=on())
    cookie = session_cookie(made)
    assert "max-age" not in cookie and "expires" not in cookie and "httponly" in cookie


def test_with_remember_me_the_sign_in_is_kept(api):
    made = api.post("/api/accounts/signup", json={**MARI, "remember": True}, headers=on())
    assert "max-age" in session_cookie(made)


def test_signing_in_with_the_pin_follows_the_remember_me_choice(api):
    uid = api.post("/api/accounts/signup", json=MARI, headers=on()).json()["user_id"]
    plain = api.post("/api/accounts/signin", json={"user_id": uid, "pin": PIN, "remember": False}, headers=on())
    assert "max-age" not in session_cookie(plain)
    kept = api.post("/api/accounts/signin", json={"user_id": uid, "pin": PIN, "remember": True}, headers=on())
    assert "max-age" in session_cookie(kept)
    tile_only = api.post("/api/accounts/signin", json={"user_id": uid}, headers=on())  # remembered: no PIN
    assert tile_only.status_code == 200 and "max-age" in session_cookie(tile_only)
