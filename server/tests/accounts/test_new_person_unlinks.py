"""A new person's calibration is never saved for the person who used the computer before.

Found in the live test: someone was still linked, "I'm new" calibrated, and the calibration
went to that earlier person, so the website found nothing to give the new account.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.accounts import devices, mode, pending_calibration
from app.api.routes import accounts, desktop_pending
from app.services import active_user

PC = "U" * 43
PIN = "482913"
MARI = {"consent": True, "username": "mari_lapu", "mobile_number": "0917 808 2488", "pin": PIN, "pin_confirm": PIN}


@pytest.fixture(autouse=True)
def own_files(tmp_path):
    active_user.use_path(tmp_path / "active_user.json")
    pending_calibration.close_window()
    yield
    active_user.set_user_id(None)
    pending_calibration.close_window()


@pytest.fixture
def api(monkeypatch, test_database):
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    app = FastAPI()
    app.include_router(accounts.router, prefix="/api")
    app.include_router(desktop_pending.router, prefix="/api")
    return TestClient(app)


def test_im_new_unlinks_the_person_still_linked(api):
    uid = api.post("/api/accounts/signup", json=MARI, headers={devices.DEVICE_HEADER: PC}).json()["user_id"]
    assert active_user.get_user_id() == uid
    assert api.post("/api/desktop/pending-calibration/allow").status_code == 200
    assert active_user.get_user_id() is None
    assert pending_calibration.new_account_allowed()


def test_sign_out_unlinks_the_person(api):
    uid = api.post("/api/accounts/signup", json=MARI, headers={devices.DEVICE_HEADER: PC}).json()["user_id"]
    assert active_user.get_user_id() == uid
    assert api.post("/api/accounts/signout", headers={devices.DEVICE_HEADER: PC}).status_code == 204
    assert active_user.get_user_id() is None
