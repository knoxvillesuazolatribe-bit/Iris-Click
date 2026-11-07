"""English/Filipino speech (extension): language per user, messages, Filipino voice fallback."""

import pytest
from sqlalchemy import select

from app.models.accessibility_settings import AccessibilitySettings
from app.models.communication import CommunicationHistory
from app.models.word_filter import FilteredWord
from app.services import tts_service, word_filter_service

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

MP3 = b"ID3fake-mp3"


@pytest.fixture
def ana(api, make_user):
    user_id = make_user("Ana Cruz")
    assert api.post("/api/assistive/select", json={"user_id": user_id}).status_code == 200
    return user_id


@pytest.fixture
def voice(monkeypatch):
    """A fake Google voice: records requests; ``fail`` simulates being offline."""
    state = {"calls": [], "fail": False}

    def engine(text, lang):
        if state["fail"]:
            raise ConnectionError("no internet")
        state["calls"].append((text, lang))
        return MP3

    monkeypatch.setattr(tts_service, "engine", engine)
    tts_service.clear_cache()
    yield state
    tts_service.clear_cache()


# --- Language per user ---------------------------------------------------------------------------

def test_language_defaults_to_english_and_is_saved(api, ana, test_database):
    assert api.get("/api/me/language").json() == {"language": "en"}
    assert api.put("/api/me/language", json={"language": "fil"}).json() == {"language": "fil"}
    assert api.get("/api/me/language").json() == {"language": "fil"}
    api.put("/api/me/language", json={"language": "fil"})  # no change: no second log
    entries = logs(test_database, "speech_language_changed")
    assert [e.activity_description for e in entries] == ["Speech language for Ana Cruz set to Filipino"]


def test_saving_a_language_does_not_touch_accessibility_settings(api, ana, test_database):
    api.put("/api/me/language", json={"language": "fil"})
    with test_database() as db:
        assert db.scalars(select(AccessibilitySettings)).all() == []  # still on the global defaults


def test_language_is_per_user(api, ana, make_user):
    api.put("/api/me/language", json={"language": "fil"})
    ben = make_user("Ben Reyes")
    api.post("/api/assistive/select", json={"user_id": ben})
    assert api.get("/api/me/language").json() == {"language": "en"}


@pytest.mark.parametrize("value", ["tl", "fil-PH", "", "EN"])
def test_only_english_or_filipino(api, ana, value):
    assert api.put("/api/me/language", json={"language": value}).status_code == 422


def test_language_needs_an_assistive_user(api, signed_in_admin):
    assert signed_in_admin.get("/api/me/language").status_code == 403
    signed_in_admin.post("/api/auth/logout")
    assert api.put("/api/me/language", json={"language": "fil"}).status_code == 401


# --- Messages keep their language -------------------------------------------------------------------

def test_messages_store_their_language(api, ana, test_database):
    sent = api.post("/api/me/communications", json={"mode": "speech_to_text", "message": "Salamat",
                                                     "language": "fil"}).json()
    assert sent["language"] == "fil"
    old_client = api.post("/api/me/communications", json={"mode": "text_to_speech", "message": "Thank you"}).json()
    assert old_client["language"] == "en"  # a page that does not send a language still works
    with test_database() as db:
        assert [m.language for m in db.scalars(select(CommunicationHistory).order_by(
            CommunicationHistory.communication_id))] == ["fil", "en"]
    described = [e.activity_description for e in logs(test_database, "communication_sent")]
    assert described[0].endswith("message (7 characters) in Filipino")
    assert described[1].endswith(" in English")
    assert api.get("/api/me/voice").json()["messages"][0]["language"] == "en"


def test_bad_language_on_a_message_is_refused(api, ana):
    response = api.post("/api/me/communications", json={"mode": "text_to_speech", "message": "Hi",
                                                         "language": "xx"})
    assert response.status_code == 422


# --- Filipino voice fallback -------------------------------------------------------------------------

def test_filipino_voice_returns_mp3_and_is_cached(api, ana, voice):
    response = api.post("/api/tts", json={"text": "Gusto ko ng tubig"})
    assert response.status_code == 200 and response.headers["content-type"] == "audio/mpeg"
    assert response.content == MP3
    api.post("/api/tts", json={"text": "Gusto  ko ng   tubig"})  # same words: cached
    assert voice["calls"] == [("Gusto ko ng tubig", "tl")]


def test_offline_says_so_and_never_falls_back_to_english(api, ana, voice):
    voice["fail"] = True
    response = api.post("/api/tts", json={"text": "Salamat"})
    assert response.status_code == 503 and "internet" in response.json()["detail"]
    assert voice["calls"] == []


@pytest.mark.parametrize("body", [{"text": ""}, {"text": "   "}, {"text": "a" * 501},
                                  {"text": "Hello", "language": "en"}])
def test_bad_voice_requests(api, ana, voice, body):
    assert api.post("/api/tts", json=body).status_code == 422
    assert voice["calls"] == []


def test_voice_text_goes_through_the_word_filter(api, ana, voice, test_database, monkeypatch, tmp_path):
    monkeypatch.setattr(word_filter_service, "SEED_FILE", tmp_path / "none.txt")
    word_filter_service.reset_process_state()
    with test_database() as db:
        db.add(FilteredWord(word="masamangsalita1", normalized_word=word_filter_service.normalize("masamangsalita1"),
                            language="fil", type="blocked"))
        db.commit()
    word_filter_service.invalidate()
    api.post("/api/tts", json={"text": "ikaw masamangsalita1"})
    word_filter_service.reset_process_state()
    assert voice["calls"] == [("ikaw beep", "tl")]


def test_voice_needs_an_assistive_user(api, signed_in_admin, voice):
    assert signed_in_admin.post("/api/tts", json={"text": "Oo"}).status_code == 403
    signed_in_admin.post("/api/auth/logout")
    assert api.post("/api/tts", json={"text": "Oo"}).status_code == 401
    assert voice["calls"] == []
