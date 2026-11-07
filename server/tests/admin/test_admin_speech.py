"""Admin side of English/Filipino speech (extension): set a user's language, reports."""

from app.models.communication import CommunicationHistory

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


def test_admin_sets_a_users_language(admin, make_user, test_database):
    ana = make_user("Ana Cruz")
    assert admin.get(f"/api/admin/users/{ana}/language").json() == {"language": "en"}
    assert admin.put(f"/api/admin/users/{ana}/language", json={"language": "fil"}).json() == {"language": "fil"}
    assert admin.get(f"/api/admin/users/{ana}/language").json() == {"language": "fil"}
    entry = logs(test_database, "speech_language_changed")[0].activity_description
    assert entry.startswith("Speech language for Ana Cruz set to Filipino by ")


def test_admin_language_needs_an_assistive_user(admin, admin_id):
    assert admin.get(f"/api/admin/users/{admin_id}/language").status_code == 404
    assert admin.put("/api/admin/users/9999/language", json={"language": "fil"}).status_code == 404


def test_assistive_users_cannot_use_the_admin_endpoint(api, make_user):
    ana = make_user("Ana Cruz")
    api.post("/api/assistive/select", json={"user_id": ana})
    assert api.put(f"/api/admin/users/{ana}/language", json={"language": "fil"}).status_code == 403


def _messages(test_database, user_id, *languages):
    with test_database() as db:
        for n, language in enumerate(languages):
            db.add(CommunicationHistory(user_id=user_id, mode="text_to_speech", message=f"m{n}", language=language))
        db.commit()


def test_communication_report_shows_language(admin, make_user, test_database):
    ana = make_user("Ana Cruz")
    _messages(test_database, ana, "en", "fil", "fil", None)
    counts = admin.get("/api/admin/reports/communication").json()
    assert counts["columns"] == ["User", "Typed", "Spoken", "Total messages", "Last used", "English", "Filipino"]
    assert counts["rows"][0][-2:] == ["1", "2"]
    totals = {i["label"]: i["value"] for i in counts["summary"]}
    assert totals["In English"] == "1" and totals["In Filipino"] == "2" and totals["Messages"] == "4"
    with_text = admin.get("/api/admin/reports/communication?include_text=true").json()
    assert with_text["columns"] == ["Date", "User", "Type", "Message"]  # older tests pin these
    assert sorted(r[2] for r in with_text["rows"]) == ["Typed", "Typed (English)", "Typed (Filipino)",
                                                       "Typed (Filipino)"]
    assert {i["label"]: i["value"] for i in with_text["summary"]}["In Filipino"] == "2"
    assert admin.get("/api/admin/reports/communication/pdf").content.startswith(b"%PDF")


def test_language_totals_are_left_out_when_no_message_has_one(admin, make_user, test_database):
    _messages(test_database, make_user("Ana Cruz"), None, None)
    labels = [i["label"] for i in admin.get("/api/admin/reports/communication").json()["summary"]]
    assert "In English" not in labels and "In Filipino" not in labels
