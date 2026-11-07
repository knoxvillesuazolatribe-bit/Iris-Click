import pytest

from app.config import get_settings

from tests.auth.conftest import (  # noqa: F401  (fixtures shared with the auth tests)
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    add_calibration,
    admin_id,
    api,
    fresh_throttle,
    logs,
    make_user,
    profiles_dir,
    signed_in_admin,
)

ENV_DEFAULTS = {"dwell_click_enabled": False, "dwell_ms": 700, "cursor_smoothing": 0.25,
                "blink_click_enabled": True, "blink_threshold": 0.18, "edge_scroll_enabled": True,
                "app_name": "IrisClick", "smtp_host": "", "smtp_from": "", "smtp_username": ""}


@pytest.fixture
def env(profiles_dir, monkeypatch):
    """Fixed .env values for every route module that reads settings."""
    settings = get_settings().model_copy(update={**ENV_DEFAULTS, "profiles_dir": profiles_dir})
    for module in ("accessibility", "admin_settings", "admin_users", "admin_reports", "home"):
        monkeypatch.setattr(f"app.api.routes.{module}.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.sos_service.get_settings", lambda: settings)
    return settings


@pytest.fixture
def admin(signed_in_admin, env):
    return signed_in_admin


def sign_in_as(api, user_id):
    assert api.post("/api/assistive/select", json={"user_id": user_id}).status_code == 200
