"""D1: with accounts on this computer and no access code set, the online copy opens without one."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.accounts import mode
from app.cloud import access

CODE = "pdao-office-code-2026"


@pytest.fixture
def site():
    app = FastAPI()
    app.middleware("http")(access.gate("/api"))
    app.include_router(access.router, prefix="/api")

    @app.get("/api/private")
    def private():
        return {"ok": True}

    return TestClient(app)


def setup(monkeypatch, signin_mode, code):
    monkeypatch.setenv(mode.ENV_NAME, signin_mode)
    if code:
        monkeypatch.setenv(access.CODE_ENV, code)
    else:
        monkeypatch.delenv(access.CODE_ENV, raising=False)


def test_new_mode_without_a_code_opens_the_site(site, monkeypatch):
    setup(monkeypatch, "device_accounts", None)
    assert site.get("/api/cloud/status").json() == {"online_copy": True, "ready": True, "access": True}
    assert site.get("/api/private").json() == {"ok": True}


def test_legacy_mode_without_a_code_stays_closed(site, monkeypatch):
    setup(monkeypatch, "legacy", None)
    assert site.get("/api/cloud/status").json()["ready"] is False
    closed = site.get("/api/private")
    assert closed.status_code == 503 and closed.json()["code"] == "not_set_up"


@pytest.mark.parametrize("signin_mode", ["legacy", "device_accounts"])
def test_a_code_that_is_set_is_always_required(site, monkeypatch, signin_mode):
    setup(monkeypatch, signin_mode, CODE)
    assert site.get("/api/cloud/status").json()["access"] is False
    assert site.get("/api/private").status_code == 401
    assert site.post("/api/cloud/access", json={"code": CODE}).status_code == 200
    assert site.get("/api/private").json() == {"ok": True}
