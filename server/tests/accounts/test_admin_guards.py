"""Build step 13: with accounts on this computer, the old-only routes answer 403 (plan H1-H8, A4).

In legacy mode (the default) the same routes behave exactly as before; here that shows as
"not signed in" (401) instead of the new 403, since the guard steps aside.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.accounts import guards, mode
from app.api.routes import admin_settings, admin_speech, admin_users, admin_voice_settings, assistive
from app.cloud import computers

GUARDED = [
    ("post", "/api/admin/users", guards.PEOPLE_CREATE),                       # H1
    ("put", "/api/admin/users/1/settings", guards.PEOPLE_SET),                # H3
    ("post", "/api/admin/users/1/settings/reset", guards.PEOPLE_SET),         # H3
    ("put", "/api/admin/users/1/voice-settings", guards.PEOPLE_SET),          # H4
    ("post", "/api/admin/users/1/voice-settings/reset", guards.PEOPLE_SET),   # H4
    ("put", "/api/admin/users/1/language", guards.PEOPLE_SET),                # H5
    ("put", "/api/admin/settings/defaults", guards.NO_GLOBAL_DEFAULTS),       # H8
    ("post", "/api/admin/settings/defaults/reset", guards.NO_GLOBAL_DEFAULTS),  # H8
    ("post", "/api/admin/users/1/computers/link", guards.ADDED_ON_COMPUTER),  # H6
    ("post", "/api/admin/users/1/computers/this", guards.ADDED_ON_COMPUTER),  # H6
]
NAME_TILES = [("get", "/api/assistive/users"), ("post", "/api/assistive/select")]  # A4


def app_with(*routers) -> TestClient:
    app = FastAPI()
    for router in routers:
        app.include_router(router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def pc():
    return app_with(admin_users.router, admin_voice_settings.router, admin_speech.router,
                    admin_settings.router, computers.admin_router, assistive.router)


@pytest.fixture
def online():
    return app_with(computers.sign_in_router)


def call(client, method, path):
    return getattr(client, method)(path, json={}) if method != "get" else client.get(path)


@pytest.mark.parametrize(("method", "path", "message"), GUARDED)
def test_admin_routes_people_now_do_themselves_answer_403(pc, monkeypatch, test_database, method, path, message):
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    response = call(pc, method, path)
    assert response.status_code == 403
    assert response.json() == {"detail": message}
    assert response.headers["X-IrisClick-Code"] == guards.CODE


@pytest.mark.parametrize(("method", "path", "message"), GUARDED)
def test_in_legacy_mode_the_guard_steps_aside(pc, monkeypatch, test_database, method, path, message):
    monkeypatch.setenv(mode.ENV_NAME, "legacy")
    response = call(pc, method, path)
    assert response.status_code != 403 and "X-IrisClick-Code" not in response.headers


@pytest.mark.parametrize(("method", "path"), NAME_TILES)
def test_no_pin_name_sign_in_is_closed_on_the_pc_and_online(pc, online, monkeypatch, test_database, method, path):
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    for client in (pc, online):
        response = call(client, method, path)
        assert response.status_code == 403
        assert response.json() == {"detail": guards.USE_YOUR_PIN}


def test_name_tiles_still_work_in_legacy_mode(pc, monkeypatch, test_database):
    monkeypatch.setenv(mode.ENV_NAME, "legacy")
    assert pc.get("/api/assistive/users").status_code == 200


def test_reading_stays_open_so_the_tracker_still_gets_settings(pc, monkeypatch, test_database):
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    response = pc.get("/api/admin/settings/defaults")
    assert "X-IrisClick-Code" not in response.headers
