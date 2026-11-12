"""The account routes inside the real apps: the PC server (app/api/main.py) and the hosted copy (app/cloud)."""

from fastapi.testclient import TestClient

from app.accounts import devices, mode
from app.api import main as pc
from app.cloud import access
from app.cloud import main as cloud
from app.config import get_settings
from app.services import session_service

CODE = "test-access-code"
PC1 = "C" * 43
PIN = "482913"
MARI = {"consent": True, "username": "mari_lapu", "mobile_number": "09178082488", "pin": PIN, "pin_confirm": PIN}


def hosted():
    return TestClient(cloud.VercelPaths(cloud.create_app()), base_url="https://irisclick.example")


def test_the_new_settings_have_the_planned_defaults():
    settings = get_settings()
    assert (settings.remember_days, settings.shared_idle_minutes, settings.signups_per_device_per_day,
            settings.accounts_per_mobile) == (30, 10, 5, 3)


def test_the_pc_server_serves_the_account_routes(monkeypatch, test_database):
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    client = TestClient(pc.create_app())
    assert client.get("/api/signin/mode").json()["mode"] == "device_accounts"
    made = client.post("/api/accounts/signup", json=MARI, headers={devices.DEVICE_HEADER: PC1})
    assert made.status_code == 201 and session_service.COOKIE_NAME in client.cookies
    assert client.get("/api/accounts/tiles", headers={devices.DEVICE_HEADER: PC1}).json()["accounts"][0][
        "username"] == "mari_lapu"


def test_the_pc_server_keeps_them_closed_in_legacy_mode(monkeypatch, test_database):
    monkeypatch.setenv(mode.ENV_NAME, "legacy")
    client = TestClient(pc.create_app())
    assert client.get("/api/signin/mode").json()["mode"] == "legacy"
    assert client.post("/api/accounts/signup", json=MARI, headers={devices.DEVICE_HEADER: PC1}).status_code == 403
    assert client.get("/api/assistive/users").status_code == 200  # today's name tiles still work


def test_on_the_hosted_copy_only_the_mode_is_open_before_the_access_code(monkeypatch, test_database):
    monkeypatch.setenv(access.CODE_ENV, CODE)
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    monkeypatch.setattr(access, "sleep", lambda _s: None)
    with hosted() as web:
        assert web.get("/api/signin/mode").json() == {"mode": "device_accounts", "sms_enabled": False}
        for method, path in [("get", "/api/accounts/tiles"), ("post", "/api/accounts/signup"),
                             ("post", "/api/accounts/signin"), ("post", "/api/accounts/username-check")]:
            response = getattr(web, method)(path, headers={devices.DEVICE_HEADER: PC1})
            assert response.status_code == 401 and response.json()["code"] == "access_required", path
        assert web.post("/api/cloud/access", json={"code": CODE}).status_code == 200
        made = web.post("/api/accounts/signup", json=MARI, headers={devices.DEVICE_HEADER: PC1})
        assert made.status_code == 201 and made.json()["username"] == "mari_lapu"


def test_the_hosted_copy_in_legacy_mode_answers_as_before(monkeypatch, test_database):
    monkeypatch.setenv(access.CODE_ENV, CODE)
    monkeypatch.setenv(mode.ENV_NAME, "legacy")
    with hosted() as web:
        assert web.get("/api/signin/mode").json()["mode"] == "legacy"
        assert web.post("/api/cloud/access", json={"code": CODE}).status_code == 200
        assert web.get("/api/accounts/tiles", headers={devices.DEVICE_HEADER: PC1}).status_code == 403
        assert web.get("/api/assistive/users").status_code == 200
