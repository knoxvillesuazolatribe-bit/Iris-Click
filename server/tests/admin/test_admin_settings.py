"""Global defaults, app name and email test (Phase 8)."""

import smtplib

import pytest
from pydantic import SecretStr

from app.services import active_user, sos_delivery, sos_service
from app.workers import user_settings

from tests.admin.conftest import logs, sign_in_as

ENV = {"dwell_enabled": False, "dwell_ms": 700, "smoothing": "medium", "blink_to_click": True,
       "blink_sensitivity": 3, "edge_scroll_enabled": True, "voice_volume": 100}
GLOBAL = {"dwell_enabled": True, "dwell_ms": 1000, "smoothing": "high", "blink_to_click": True,
          "blink_sensitivity": 4, "edge_scroll_enabled": False, "voice_volume": 80}


def _values(body):
    return {k: body[k] for k in ENV}


# --- Global accessibility defaults ----------------------------------------------------------

def test_defaults_start_as_the_env_values(admin):
    body = admin.get("/api/admin/settings/defaults").json()
    assert _values(body) == ENV and body["is_default"] is True
    assert body["env_defaults"] == ENV


def test_global_defaults_reach_users_without_their_own(admin, api, make_user, test_database):
    saved = admin.put("/api/admin/settings/defaults", json=GLOBAL).json()
    assert _values(saved) == GLOBAL and saved["is_default"] is False
    assert len(logs(test_database, "settings_defaults_updated")) == 1

    ana = make_user("Ana Cruz")
    admin.post("/api/auth/logout")
    sign_in_as(api, ana)
    mine = api.get("/api/me/settings").json()
    assert _values(mine) == GLOBAL and mine["is_default"] is True
    assert mine["defaults"] == GLOBAL
    assert api.get("/api/me/voice").json()["voice_volume"] == 80
    guide = {g["gesture"]: g["action"] for g in api.get("/api/me/home").json()["gestures"]}
    assert guide["Keep looking at one spot"] == "Clicks after 1 second"


def test_a_users_own_settings_win_over_global(admin, make_user):
    admin.put("/api/admin/settings/defaults", json=GLOBAL)
    ana = make_user("Ana Cruz")
    own = {**GLOBAL, "dwell_ms": 500, "voice_volume": 30}
    admin.put(f"/api/admin/users/{ana}/settings", json=own)
    assert _values(admin.get(f"/api/admin/users/{ana}/settings").json()) == own


def test_reset_returns_to_env(admin, test_database):
    admin.put("/api/admin/settings/defaults", json=GLOBAL)
    body = admin.post("/api/admin/settings/defaults/reset").json()
    assert _values(body) == ENV and body["is_default"] is True
    assert len(logs(test_database, "settings_defaults_reset")) == 1


def test_global_defaults_keep_a_way_to_click(admin):
    response = admin.put("/api/admin/settings/defaults",
                         json={**GLOBAL, "dwell_enabled": False, "blink_to_click": False})
    assert response.status_code == 422


def test_tracking_worker_uses_global_then_user_settings(admin, env, make_user):
    admin.put("/api/admin/settings/defaults", json=GLOBAL)
    active_user.set_user_id(None)
    loaded = user_settings.for_active_user(env)
    assert (loaded.dwell_click_enabled, loaded.dwell_ms, loaded.cursor_smoothing,
            loaded.blink_threshold, loaded.edge_scroll_enabled) == (True, 1000, 0.45, 0.20, False)

    ana = make_user("Ana Cruz")
    admin.put(f"/api/admin/users/{ana}/settings", json={**GLOBAL, "dwell_ms": 500})
    active_user.set_user_id(ana)
    assert user_settings.for_active_user(env).dwell_ms == 500


# --- System ------------------------------------------------------------------------------------

def test_system_shows_email_status_without_secrets(admin, env, monkeypatch):
    body = admin.get("/api/admin/settings/system").json()
    assert body["email"]["configured"] is False and body["sms_configured"] is False
    configured = env.model_copy(update={"smtp_host": "smtp.gmail.com", "smtp_username": "sos@x.co",
                                        "smtp_password": SecretStr("very-secret")})
    monkeypatch.setattr("app.api.routes.admin_settings.get_settings", lambda: configured)
    response = admin.get("/api/admin/settings/system")
    assert response.json()["email"] == {"configured": True, "host": "smtp.gmail.com", "port": 587,
                                        "security": "starttls", "from_address": "sos@x.co"}
    assert "very-secret" not in response.text


def test_app_name_is_saved_shown_and_used_in_sos(admin, api, env, test_database):
    from app.models.timestamps import utc_now
    from app.models.user import User
    from app.services.system_settings_service import app_name

    admin.put("/api/admin/settings/system/app-name", json={"app_name": "  PDAO IrisClick "})
    assert api.get("/api/app-info").json() == {"app_name": "PDAO IrisClick"}
    assert "PDAO IrisClick" in logs(test_database, "app_name_updated")[0].activity_description
    with test_database() as session:
        body = sos_service.build_message(User(full_name="Ana"), None, utc_now(),
                                         app_name(session, env))
    assert "Sent by PDAO IrisClick" in body
    admin.put("/api/admin/settings/system/app-name", json={"app_name": "   "})
    assert api.get("/api/app-info").json() == {"app_name": "IrisClick"}


class FakeSMTP:
    sent: list = []
    fail = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        pass

    def send_message(self, message):
        if FakeSMTP.fail:
            raise FakeSMTP.fail
        FakeSMTP.sent.append(message)


@pytest.fixture
def smtp(env, monkeypatch):
    FakeSMTP.sent, FakeSMTP.fail = [], None
    monkeypatch.setattr(sos_delivery.smtplib, "SMTP", FakeSMTP)
    configured = env.model_copy(update={"smtp_host": "smtp.example.com", "smtp_username": "sos@x.co"})
    monkeypatch.setattr("app.api.routes.admin_settings.get_settings", lambda: configured)
    return FakeSMTP


def test_test_email_really_sends_and_is_logged(admin, smtp, test_database):
    result = admin.post("/api/admin/settings/system/test-email", json={"to": "me@example.com"}).json()
    assert result["sent"] is True
    assert smtp.sent[0]["To"] == "me@example.com"
    assert "sent" in logs(test_database, "email_test")[0].activity_description


def test_test_email_failure_shows_the_reason(admin, smtp):
    smtp.fail = smtplib.SMTPAuthenticationError(535, b"bad")
    result = admin.post("/api/admin/settings/system/test-email", json={"to": "me@example.com"}).json()
    assert result["sent"] is False
    assert "app password was refused" in result["detail"]


def test_test_email_when_not_set_up(admin):
    result = admin.post("/api/admin/settings/system/test-email", json={"to": "me@example.com"}).json()
    assert result == {"sent": False, "detail": sos_delivery.EMAIL_NOT_SET_UP}


def test_sms_test_is_honest(admin):
    assert admin.post("/api/admin/settings/system/test-sms").json() == {
        "sent": False, "detail": sos_delivery.SMS_NOT_SET_UP}
