"""PDAO setup codes are switched off by default (SETUP_CODES); everything stays to turn them back on."""

import pytest

from app.accounts import setup_codes
from tests.accounts.test_setup_codes import api, make_code, on, people, secret  # noqa: F401


@pytest.fixture
def codes_off(monkeypatch, tmp_path):
    monkeypatch.delenv(setup_codes.ENV_NAME, raising=False)
    # No SETUP_CODES in any .env either: an empty one stands in for server/.env.
    empty = tmp_path / ".env"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setattr(setup_codes, "enabled", lambda env_file=None, _e=setup_codes.enabled: _e(empty))


def test_off_unless_switched_on(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    monkeypatch.delenv(setup_codes.ENV_NAME, raising=False)
    assert setup_codes.enabled(env) is False
    for value in ("on", "ON", "1", "true", "yes"):
        monkeypatch.setenv(setup_codes.ENV_NAME, value)
        assert setup_codes.enabled(env) is True
    monkeypatch.setenv(setup_codes.ENV_NAME, "off")
    assert setup_codes.enabled(env) is False


def test_server_env_file_can_switch_them_on(monkeypatch, tmp_path):
    monkeypatch.delenv(setup_codes.ENV_NAME, raising=False)
    env = tmp_path / ".env"
    env.write_text("SETUP_CODES=on\n", encoding="utf-8")
    assert setup_codes.enabled(env) is True


def test_admins_cannot_make_codes_while_off(test_database, codes_off):
    admin, mari = people(test_database)
    with pytest.raises(setup_codes.SetupCodeError) as refused:
        make_code(test_database, admin, mari)
    assert refused.value.code == "setup_codes_off" and refused.value.status_code == 404


def test_a_code_made_earlier_stops_working_while_off(test_database, api, monkeypatch, tmp_path):  # noqa: F811
    admin, mari = people(test_database)
    code = make_code(test_database, admin, mari)  # made while on
    monkeypatch.setenv(setup_codes.ENV_NAME, "off")
    answer = api.post("/api/accounts/setup-code", json={"code": code}, headers=on())
    assert answer.status_code == 404 and answer.json()["code"] == "setup_codes_off"
    done = api.post("/api/accounts/setup-complete", headers=on(),
                    json={"ticket": "x", "pin": "482913", "pin_confirm": "482913"})
    assert done.status_code == 404 and done.json()["code"] == "setup_codes_off"


def test_the_site_is_told_whether_setup_codes_are_on(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes import accounts

    app = FastAPI()
    app.include_router(accounts.mode_router, prefix="/api")
    site = TestClient(app)
    monkeypatch.setenv(setup_codes.ENV_NAME, "off")
    assert site.get("/api/signin/mode").json()["setup_codes_enabled"] is False
    monkeypatch.setenv(setup_codes.ENV_NAME, "on")
    assert site.get("/api/signin/mode").json()["setup_codes_enabled"] is True
