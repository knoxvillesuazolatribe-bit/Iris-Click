"""Admin Word Filter page (extension). Dummy words only; logs name words by id only."""

import pytest

from app.models.communication import CommunicationHistory
from app.services import word_filter_service as wf

from tests.admin.conftest import logs, sign_in_as  # noqa: F401
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

BASE = "/api/admin/word-filter"


@pytest.fixture(autouse=True)
def fresh_filter(monkeypatch, tmp_path):
    monkeypatch.setattr(wf, "SEED_FILE", tmp_path / "none.txt")
    wf.reset_process_state()
    yield
    wf.reset_process_state()


def add(admin, word, language="en", kind="blocked"):
    return admin.post(f"{BASE}/words", json={"word": word, "language": language, "type": kind})


def masked(text):
    from app.models import database
    with database.get_session_factory()() as db:
        return wf.check(db, text).masked_text


def no_words_in_logs(test_database, *words):
    for entry in logs(test_database):
        for word in words:
            assert word not in (entry.activity_description or "").lower()


def test_add_remove_restore_with_id_only_logs(admin, test_database):
    response = add(admin, "badword1")
    assert response.status_code == 201
    word_id = response.json()["word_id"]
    assert masked("x badword1") == "x b*******"
    removed = admin.delete(f"{BASE}/words/{word_id}")
    assert removed.status_code == 200 and removed.json()["is_active"] is False
    assert masked("x badword1") == "x badword1"
    assert admin.post(f"{BASE}/words/{word_id}/restore").json()["is_active"] is True
    assert masked("x badword1") == "x b*******"
    assert [len(logs(test_database, f"word_filter_{v}")) for v in ("added", "removed", "restored")] == [1, 1, 1]
    assert f"word #{word_id}" in logs(test_database, "word_filter_added")[0].activity_description
    no_words_in_logs(test_database, "badword1")


def test_duplicates_and_bad_input(admin):
    add(admin, "badword1")
    response = add(admin, "B@DW0RD1")  # same word once normalized
    assert response.status_code == 409 and "already" in response.json()["detail"]
    assert "badword1" not in response.json()["detail"].lower()
    assert add(admin, "!!!").status_code == 422
    assert admin.post(f"{BASE}/words", json={"word": "x", "language": "xx"}).status_code == 422
    assert admin.delete(f"{BASE}/words/9999").status_code == 404


def test_adding_a_removed_word_brings_it_back(admin, test_database):
    word_id = add(admin, "badword1").json()["word_id"]
    admin.delete(f"{BASE}/words/{word_id}")
    again = add(admin, "badword1", language="fil")
    assert again.status_code == 201 and again.json()["word_id"] == word_id
    assert again.json()["language"] == "fil" and again.json()["is_active"] is True


def test_list_search_and_filters(admin):
    add(admin, "badword1")
    add(admin, "masamangsalita1", language="fil")
    add(admin, "baddword", kind="allowed")
    gone = add(admin, "badword2").json()["word_id"]
    admin.delete(f"{BASE}/words/{gone}")
    names = lambda r: [w["word"] for w in r.json()]  # noqa: E731
    assert names(admin.get(f"{BASE}/words")) == ["baddword", "badword1", "masamangsalita1"]
    assert names(admin.get(f"{BASE}/words?language=fil")) == ["masamangsalita1"]
    assert names(admin.get(f"{BASE}/words?type=allowed")) == ["baddword"]
    assert names(admin.get(f"{BASE}/words?status=removed")) == ["badword2"]
    assert len(admin.get(f"{BASE}/words?status=all").json()) == 4
    assert names(admin.get(f"{BASE}/words?q=MASA")) == ["masamangsalita1"]


def test_import_txt_and_csv(admin, test_database):
    add(admin, "badword1")
    content = "# comment\nword,language,type\nbadword1,en\nmasamangsalita1,fil\nbaddword,en,allowed\n\nbadword2\n!!!\n"
    body = admin.post(f"{BASE}/import", json={"content": content}).json()
    assert body == {"added": 3, "restored": 0, "skipped": 2}
    assert masked("masamangsalita1 badword2 baddword") == "m************** b******* baddword"
    entry = logs(test_database, "word_filter_imported")[0].activity_description
    assert "3 added" in entry
    no_words_in_logs(test_database, "badword", "masamangsalita")


def test_export_csv_and_txt(admin, test_database):
    add(admin, "badword1")
    add(admin, "masamangsalita1", language="fil")
    csv_file = admin.get(f"{BASE}/export?format=csv")
    assert csv_file.headers["content-type"].startswith("text/csv")
    assert 'filename="irisclick_word_filter.csv"' in csv_file.headers["content-disposition"]
    assert csv_file.text.splitlines() == ["word,language,type", "badword1,en,blocked", "masamangsalita1,fil,blocked"]
    txt = admin.get(f"{BASE}/export?format=txt").text
    assert "badword1,en,blocked" in txt and txt.startswith("#")
    assert len(logs(test_database, "word_filter_exported")) == 2
    # An export can be imported again without changes.
    assert admin.post(f"{BASE}/import", json={"content": csv_file.text}).json()["skipped"] == 2


def test_on_off_and_beep_skip(admin, test_database):
    add(admin, "badword1")
    assert admin.get(f"{BASE}/settings").json() == {"enabled": True, "tts_mode": "beep"}
    assert admin.put(f"{BASE}/settings", json={"enabled": False}).json()["enabled"] is False
    assert masked("badword1") == "badword1"
    admin.put(f"{BASE}/settings", json={"enabled": True, "tts_mode": "skip"})
    assert masked("badword1") == "b*******"
    assert admin.put(f"{BASE}/settings", json={"tts_mode": "loud"}).status_code == 422
    toggles = [l.activity_description for l in logs(test_database, "word_filter_toggled")]
    assert len(toggles) == 2 and "turned off" in toggles[0] and "speech set to skip" in toggles[1]


def test_communication_report_masks_old_messages_too(admin, make_user, test_database):
    ana = make_user("Ana Cruz")
    with test_database() as db:  # saved before the word was added to the list
        db.add(CommunicationHistory(user_id=ana, mode="text_to_speech", message="old badword1 message"))
        db.commit()
    add(admin, "badword1")
    rows = admin.get("/api/admin/reports/communication?include_text=true").json()["rows"]
    assert rows[0][-1] == "old b******* message"


def test_word_filter_is_admin_only(api, make_user):
    assert api.get(f"{BASE}/words").status_code == 401
    sign_in_as(api, make_user("Ana Cruz"))
    for response in (api.get(f"{BASE}/words"), api.get(f"{BASE}/settings"), add(api, "badword1"),
                     api.post(f"{BASE}/import", json={"content": "x"}), api.get(f"{BASE}/export")):
        assert response.status_code == 403
