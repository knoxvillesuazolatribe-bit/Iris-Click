"""Add your address (build step 12): the person sets the address sent with an SOS alert."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.accounts import devices, mode
from app.api.routes import accounts
from app.models.system_log import SystemLog
from app.models.user import User

PC = "D" * 43
PIN = "482913"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    app = FastAPI()
    app.include_router(accounts.router, prefix="/api")
    client = TestClient(app)
    made = client.post("/api/accounts/signup", headers={devices.DEVICE_HEADER: PC}, json={
        "consent": True, "username": "mari_lapu", "mobile_number": "09178082488", "pin": PIN, "pin_confirm": PIN})
    assert made.status_code == 201
    return client


def test_a_person_adds_their_own_address(api, test_database):
    saved = api.put("/api/accounts/me/address", json={"address": "  123  Purok Mangga ", "barangay": "Pajo"})
    assert saved.status_code == 200
    assert saved.json() == {"location_text": "123 Purok Mangga, Barangay Pajo, Lapu-Lapu City"}
    with test_database() as db:
        user = db.scalars(select(User)).one()
        assert (user.address, user.barangay) == ("123 Purok Mangga", "Pajo")
        log = db.scalars(select(SystemLog).where(SystemLog.activity_type == "address_updated")).one()
        assert "Purok" not in log.activity_description and "Pajo" not in log.activity_description


def test_the_barangay_may_be_left_blank(api):
    saved = api.put("/api/accounts/me/address", json={"address": "Block 5 Lot 2"})
    assert saved.json() == {"location_text": "Block 5 Lot 2, Lapu-Lapu City"}


@pytest.mark.parametrize("body", [{"address": ""}, {"address": "   "}, {"address": "x" * 256},
                                  {"address": "Purok 1", "barangay": "y" * 101}])
def test_bad_addresses_are_refused(api, body):
    assert api.put("/api/accounts/me/address", json=body).status_code == 422


def test_only_a_signed_in_person_can_change_it(api, monkeypatch):
    api.cookies.clear()
    assert api.put("/api/accounts/me/address", json={"address": "Purok 1"}).status_code == 401
    monkeypatch.setenv(mode.ENV_NAME, "legacy")
    assert api.put("/api/accounts/me/address", json={"address": "Purok 1"}).status_code == 403
