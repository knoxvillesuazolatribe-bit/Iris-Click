"""Build step 14: the admin side of accounts on this computer."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.accounts import devices, limits, mode, service, setup_codes
from app.api.deps import require_admin
from app.api.routes import accounts, admin_accounts
from app.models.account_models import ATTEMPT_PIN, Device, DeviceAccount, UserAccount
from app.models.system_log import SystemLog
from app.models.user import User
from app.models.user_session import UserSession
from app.services import active_user, report_service

PC1, PC2 = "D" * 43, "E" * 43
PIN = "482913"
MARI = {"consent": True, "username": "mari_lapu", "mobile_number": "0917 808 2488", "pin": PIN, "pin_confirm": PIN}


def on(computer=PC1):
    return {devices.DEVICE_HEADER: computer}


@pytest.fixture(autouse=True)
def own_file(tmp_path):
    active_user.use_path(tmp_path / "active_user.json")
    yield
    active_user.set_user_id(None)


@pytest.fixture
def admin_user(test_database):
    with test_database() as db:
        admin = User(full_name="PDAO Admin", role="admin", email="admin@pdao.example",
                     password_hash="$argon2id$test-not-a-login")
        db.add(admin)
        db.commit()
        db.refresh(admin)
        db.expunge(admin)
        return admin


@pytest.fixture
def api(monkeypatch, admin_user):
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    app = FastAPI()
    app.include_router(accounts.router, prefix="/api")
    app.include_router(admin_accounts.router, prefix="/api")
    app.dependency_overrides[require_admin] = lambda: admin_user
    return TestClient(app)


@pytest.fixture
def mari(api):
    made = api.post("/api/accounts/signup", json={**MARI, "remember": True}, headers=on())
    assert made.status_code == 201
    api.post("/api/accounts/signin", json={"username": "mari_lapu", "pin": PIN}, headers=on(PC2))
    return made.json()["user_id"]


def logs(test_database, kind):
    with test_database() as db:
        return db.scalars(select(SystemLog).where(SystemLog.activity_type == kind)).all()


def test_legacy_mode_closes_the_admin_account_routes(api, monkeypatch):
    monkeypatch.setenv(mode.ENV_NAME, "legacy")
    assert api.get("/api/admin/accounts").status_code == 403


def test_users_columns_show_username_masked_mobile_and_computers(api, mari):
    [row] = api.get("/api/admin/accounts").json()
    assert row == {"user_id": mari, "username": "mari_lapu", "mobile": "09** *** 2488",
                   "mobile_verified": False, "computers": 2}
    assert "8082488" not in str(row)


def test_the_sign_in_card_and_a_person_without_an_account(api, mari, test_database):
    detail = api.get(f"/api/admin/accounts/{mari}").json()
    assert detail["lock"] == "ok" and detail["must_reset_pin"] is False and detail["shared_computers"] == 0
    with test_database() as db:
        john = User(full_name="John", role="assistive_user")
        db.add(john)
        db.commit()
        assert api.get(f"/api/admin/accounts/{john.user_id}").status_code == 404


def test_reset_pin_shows_a_setup_code_once_and_never_stores_it(api, mari, test_database):
    made = api.post(f"/api/admin/accounts/{mari}/reset-pin")
    assert made.status_code == 200 and made.headers["Cache-Control"] == "no-store"
    code = made.json()["code"].replace(" ", "")
    assert setup_codes.is_code(code)
    with test_database() as db:
        assert db.get(UserAccount, mari).must_reset_pin is True
        assert all(code not in (row.activity_description or "") for row in db.scalars(select(SystemLog)))
    assert len(logs(test_database, "pin_reset_by_admin")) == 1
    redeemed = api.post("/api/accounts/setup-code", json={"code": code}, headers=on())
    assert redeemed.status_code == 200


def test_unlock_clears_wrong_tries_on_every_computer(api, mari, test_database):
    with test_database() as db:
        for device in db.scalars(select(Device)).all():
            for _ in range(limits.PIN_TRIES_BEFORE_WAIT):
                limits.record_wrong_try(db, ATTEMPT_PIN, device_id=device.device_id, user_id=mari)
    assert api.get(f"/api/admin/accounts/{mari}").json()["lock"] == "locked"
    assert api.post(f"/api/admin/accounts/{mari}/unlock").status_code == 204
    assert api.get(f"/api/admin/accounts/{mari}").json()["lock"] == "ok"
    assert len(logs(test_database, "pin_unlocked_by_admin")) == 1


def test_sign_out_everywhere_ends_sessions_and_remember_me(api, mari, test_database):
    active_user.set_user_id(mari)
    assert api.post(f"/api/admin/accounts/{mari}/sign-out-everywhere").status_code == 204
    with test_database() as db:
        assert all(s.revoked_at is not None for s in db.scalars(select(UserSession)).all())
        assert not any(link.remembered for link in db.scalars(select(DeviceAccount)).all())
        device = devices.find_device(db, PC1)
        assert service.list_tiles(db, device)[0].needs_pin is True
    assert active_user.get_user_id() is None
    assert len(logs(test_database, "account_signed_out_everywhere")) == 1


def test_unknown_people_answer_404(api):
    for action in ("unlock", "sign-out-everywhere", "reset-pin"):
        assert api.post(f"/api/admin/accounts/999/{action}").status_code == 404


def test_shared_switch_for_this_computer(api, mari, test_database):
    assert api.put("/api/admin/accounts/this-computer", json={"shared": True}).status_code == 400  # no computer ID
    assert api.put("/api/admin/accounts/this-computer", json={"shared": True}, headers=on()).json() == {"shared": True}
    assert api.get("/api/accounts/this-computer", headers=on()).json()["is_shared"] is True
    with test_database() as db:
        device = devices.find_device(db, PC1)
        assert not any(link.remembered for link in db.scalars(
            select(DeviceAccount).where(DeviceAccount.device_id == device.device_id)))
    assert api.put("/api/admin/accounts/this-computer", json={"shared": False}, headers=on()).json() == {"shared": False}
    assert len(logs(test_database, "device_shared_on")) == 1 and len(logs(test_database, "device_shared_off")) == 1


def test_the_accounts_log_tab_lists_only_account_events(api, mari, test_database):
    api.post(f"/api/admin/accounts/{mari}/unlock")
    with test_database() as db:
        db.add(SystemLog(activity_type="calibration_saved", activity_description="not an account event"))
        db.commit()
        rows, total = report_service.logs(db, "accounts", None, None, 1)
    kinds = {row.activity_type for row in rows}
    assert "pin_unlocked_by_admin" in kinds and "calibration_saved" not in kinds and total == len(rows)

