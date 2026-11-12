"""Shared computers (build step 10): no Remember me, PIN to remove, idle sign-out time."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.accounts import devices, mode
from app.api.routes import accounts
from app.config import get_settings
from app.models.account_models import Device

PC = "S" * 43
PIN = "482913"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    app = FastAPI()
    app.include_router(accounts.router, prefix="/api")
    return TestClient(app)


def on():
    return {devices.DEVICE_HEADER: PC}


def test_a_computer_is_not_shared_until_the_admin_says_so(api, test_database):
    expected = get_settings().shared_idle_minutes
    assert api.get("/api/accounts/this-computer", headers=on()).json() == {"is_shared": False, "idle_minutes": expected}
    assert api.get("/api/accounts/this-computer").json()["is_shared"] is False  # no computer ID
    with test_database() as db:
        assert db.scalars(select(Device)).all() == []  # asking adds nothing


def test_a_shared_computer_says_so_and_never_remembers(api, test_database, monkeypatch):
    monkeypatch.setattr(accounts, "get_settings", lambda: get_settings().model_copy(update={"shared_idle_minutes": 3}))
    made = api.post("/api/accounts/signup", headers=on(), json={
        "consent": True, "username": "mari_lapu", "mobile_number": "09178082488", "pin": PIN, "pin_confirm": PIN,
        "remember": True})
    assert made.status_code == 201
    with test_database() as db:
        db.scalars(select(Device)).one().is_shared = True
        db.commit()
    assert api.get("/api/accounts/this-computer", headers=on()).json() == {"is_shared": True, "idle_minutes": 3}
    tiles = api.get("/api/accounts/tiles", headers=on()).json()
    assert tiles["is_shared"] is True and tiles["accounts"][0]["needs_pin"] is True
