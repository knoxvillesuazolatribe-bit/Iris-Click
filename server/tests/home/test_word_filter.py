"""Word filter (extension): matching, masking, storage, SOS bypass. Dummy words only."""

import pytest
from sqlalchemy import select

from app.models.communication import CommunicationHistory
from app.models.sos import SosHistory
from app.models.user import User
from app.models.word_filter import FilteredWord, WordFilterSettings
from app.services import sos_service, word_filter_service as wf

from tests.auth.conftest import (  # noqa: F401  (fixtures)
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    admin_id,
    api,
    fresh_throttle,
    logs,
    make_user,
    profiles_dir,
    signed_in_admin,
)


@pytest.fixture(autouse=True)
def fresh_filter(monkeypatch, tmp_path):
    """No real seed file, and no cached list from another test."""
    monkeypatch.setattr(wf, "SEED_FILE", tmp_path / "none.txt")
    wf.reset_process_state()
    yield
    wf.reset_process_state()


def add(factory, word, kind="blocked", language="en", active=True):
    with factory() as db:
        db.add(FilteredWord(word=word, normalized_word=wf.normalize_for(word, kind), language=language,
                            type=kind, is_active=active))
        db.commit()
    wf.invalidate()


@pytest.fixture
def words(test_database):
    add(test_database, "badword1")
    add(test_database, "masamangsalita1", language="fil")
    add(test_database, "dummy phrase")
    return test_database


def check(factory, text):
    with factory() as db:
        return wf.check(db, text)


# --- Matching -----------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "badword1", "BADWORD1", "BadWord1", "b@dw0rd1", "B4DW0RD!", "baaadwooord1", "badword1!",
    "b.a.d.w.o.r.d.1", "b a d w o r d 1", "b-a-d-w-o-r-d-1", "bádwórd1", "masamangsalita1",
    "MASAMANGSALITA1", "m@s@m@ngs@lit@1",
])
def test_disguised_words_are_caught(words, text):
    result = check(words, f"you {text} there")
    assert result.was_filtered and result.matches_count == 1
    assert result.masked_text.startswith("you ") and result.masked_text.endswith(" there")
    assert "*" in result.masked_text


@pytest.mark.parametrize("text", [
    "abadword1", "badword1ing", "badwords", "computation", "masamang salita", "dummy", "phrase",
    "a b c d", "", "Hello, how are you?",
])
def test_no_false_hits(words, text):
    result = check(words, text)
    assert not result.was_filtered and result.masked_text == text and result.matches_count == 0


def test_mask_keeps_the_first_letter(words):
    assert check(words, "badword1").masked_text == "b*******"
    assert check(words, "Badword1, ok?").masked_text == "B*******, ok?"


def test_phrases_match_as_a_whole(words):
    result = check(words, "this is a dummy phrase here")
    assert result.masked_text == "this is a d**** p***** here" and result.matches_count == 1
    assert not check(words, "dummy and phrase").was_filtered


def test_several_matches_are_counted(words):
    result = check(words, "badword1 and masamangsalita1 and badword1")
    assert result.matches_count == 3
    assert result.masked_text == "b******* and m************** and b*******"


def test_allowed_word_wins(test_database):
    add(test_database, "badword")
    assert check(test_database, "baddword").was_filtered  # stretched letters look like the blocked word
    add(test_database, "baddword", kind="allowed")
    assert not check(test_database, "baddword").was_filtered
    assert check(test_database, "badword").was_filtered


def test_removed_words_are_not_used(test_database):
    add(test_database, "badword1", active=False)
    assert not check(test_database, "badword1").was_filtered


def test_speech_says_beep_or_skips(words):
    assert check(words, "you badword1 there").speak_text == "you beep there"
    with words() as db:
        db.add(WordFilterSettings(setting_id=1, enabled=True, tts_mode="skip"))
        db.commit()
    wf.invalidate()
    assert check(words, "you badword1 there").speak_text == "you there"


def test_filter_can_be_turned_off(words):
    with words() as db:
        db.add(WordFilterSettings(setting_id=1, enabled=False, tts_mode="beep"))
        db.commit()
    wf.invalidate()
    result = check(words, "badword1")
    assert result.masked_text == "badword1" and not result.was_filtered


# --- Seed file ----------------------------------------------------------------------------------

def test_seed_file_adds_new_lines_once_and_never_re_adds_removed(test_database, tmp_path, monkeypatch):
    seed = tmp_path / "seed.txt"
    seed.write_text("# header\n\nbadword1,en\nmasamangsalita1,fil\nword,language\nbadword1,en\n", encoding="utf-8")
    monkeypatch.setattr(wf, "SEED_FILE", seed)
    wf.reset_process_state()
    assert check(test_database, "badword1 masamangsalita1").matches_count == 2
    with test_database() as db:
        rows = db.scalars(select(FilteredWord).order_by(FilteredWord.word_id)).all()
        assert [(r.word, r.language) for r in rows] == [("badword1", "en"), ("masamangsalita1", "fil")]
        rows[0].is_active = False
        db.commit()
    wf.reset_process_state()  # a server restart
    assert check(test_database, "badword1").was_filtered is False
    seeded = logs(test_database, "word_filter_seeded")
    assert len(seeded) == 1 and "badword1" not in seeded[0].activity_description


# --- Saving and speaking ------------------------------------------------------------------------

@pytest.fixture
def ana(api, make_user):
    user_id = make_user("Ana Cruz")
    assert api.post("/api/assistive/select", json={"user_id": user_id}).status_code == 200
    return user_id


def test_only_masked_text_is_stored(api, ana, words):
    response = api.post("/api/me/communications", json={"mode": "speech_to_text", "message": "hi badword1 hi"})
    assert response.status_code == 201 and response.json()["message"] == "hi b******* hi"
    with words() as db:
        row = db.scalars(select(CommunicationHistory)).one()
        assert row.message == "hi b******* hi" and row.was_filtered is True
    for entry in logs(words):
        assert "badword1" not in (entry.activity_description or "")


def test_clean_messages_are_stored_as_written(api, ana, words):
    api.post("/api/me/communications", json={"mode": "text_to_speech", "message": "I need water"})
    with words() as db:
        row = db.scalars(select(CommunicationHistory)).one()
        assert row.message == "I need water" and row.was_filtered is False


def test_check_endpoint_for_speaking(api, ana, words):
    body = api.post("/api/me/filter/check", json={"text": "say masamangsalita1 now"}).json()
    assert body == {"masked_text": "say m************** now", "was_filtered": True, "matches_count": 1,
                    "speak_text": "say beep now"}


def test_check_endpoint_needs_an_assistive_user(api, signed_in_admin):
    assert signed_in_admin.post("/api/me/filter/check", json={"text": "x"}).status_code == 403
    signed_in_admin.post("/api/auth/logout")
    assert api.post("/api/me/filter/check", json={"text": "x"}).status_code == 401


def test_a_broken_filter_never_blocks_saving(api, ana, words, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("filter bug")

    monkeypatch.setattr(wf, "check", broken)
    response = api.post("/api/me/communications", json={"mode": "text_to_speech", "message": "hello badword1"})
    assert response.status_code == 201 and response.json()["message"] == "hello badword1"


# --- SOS is never filtered ----------------------------------------------------------------------

def test_sos_alerts_are_never_filtered(words, make_user, monkeypatch):
    user_id = make_user("Badword1 Cruz")
    monkeypatch.setattr(wf, "check", lambda *_a, **_k: pytest.fail("the filter ran on an SOS alert"))
    monkeypatch.setattr(sos_service.dispatcher, "submit", lambda *_a, **_k: None)
    with words() as db:
        user = db.get(User, user_id)
        sos_service.add_contact(db, user, {"contact_name": "Test", "email_address": "test@example.com"})
        sos_service.activate(db, user, "00000000-0000-4000-8000-000000000001")
        row = db.scalars(select(SosHistory)).one()
        assert "EMERGENCY SOS: Badword1 Cruz needs help." in row.message_sent
