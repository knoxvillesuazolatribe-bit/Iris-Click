"""Admin: a user's voice settings (clearer TTS)."""

from tests.admin.conftest import logs  # noqa: F401
from tests.admin.conftest import (  # noqa: F401  (fixtures)
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    admin,
    admin_id,
    api,
    env,
    fresh_throttle,
    make_user,
    profiles_dir,
    signed_in_admin,
)


def test_admin_sets_and_resets_a_users_voice(admin, make_user, test_database):
    ana = make_user("Ana Cruz")
    base = f"/api/admin/users/{ana}/voice-settings"
    assert admin.get(base).json()["voice_en"] == "en-PH-RosaNeural"
    body = admin.put(base, json={"voice_en": "en-PH-JamesNeural", "rate": -25}).json()
    assert (body["voice_en"], body["rate"]) == ("en-PH-JamesNeural", -25)
    assert admin.post(f"{base}/reset").json()["voice_en"] == "en-PH-RosaNeural"
    changed = logs(test_database, "voice_settings_changed")[0].activity_description
    assert changed.startswith("Voice settings for Ana Cruz changed (English voice James, speed -25) by ")
    assert len(logs(test_database, "voice_settings_reset")) == 1


def test_admin_voice_settings_rules(admin, admin_id, make_user):
    assert admin.get(f"/api/admin/users/{admin_id}/voice-settings").status_code == 404
    ana = make_user("Ana Cruz")
    assert admin.put(f"/api/admin/users/{ana}/voice-settings", json={"rate": 99}).status_code == 422


def test_assistive_users_cannot_use_the_admin_endpoint(api, make_user):
    ana = make_user("Ana Cruz")
    api.post("/api/assistive/select", json={"user_id": ana})
    assert api.get(f"/api/admin/users/{ana}/voice-settings").status_code == 403
