"""Clearer text to speech: neural voice, cache, timeout, settings. Microsoft is never called."""

import asyncio
import base64
import os
import sys
import types

import pytest
from sqlalchemy import select

from app.models.accessibility_settings import AccessibilitySettings
from app.models.word_filter import FilteredWord
from app.services import neural_tts_service as tts
from app.services import word_filter_service

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

MARKS = [{"offset_ms": 50, "duration_ms": 300, "text": "word"}]


@pytest.fixture
def voice(monkeypatch, tmp_path):
    """A fake neural engine; ``fail`` simulates being offline. Jobs run inline."""
    state = {"calls": [], "fail": False}

    def engine(text, voice_id, rate, pitch):
        if state["fail"]:
            raise ConnectionError("offline")
        state["calls"].append((text, voice_id, rate, pitch))
        return f"MP3:{voice_id}:{text}".encode(), MARKS

    monkeypatch.setattr(tts, "engine", engine)
    monkeypatch.setattr(tts, "cache_dir", tmp_path / "tts_cache")
    monkeypatch.setattr(tts, "runner", lambda fn: fn())
    return state


@pytest.fixture
def ana(api, make_user):
    user_id = make_user("Ana Cruz")
    assert api.post("/api/assistive/select", json={"user_id": user_id}).status_code == 200
    return user_id


def say(api, text, language="en", **extra):
    return api.post("/api/tts/speak", json={"text": text, "language": language, **extra})


# --- Voice choice and settings ----------------------------------------------------------------

def test_defaults_per_language(api, ana, voice):
    body = api.get("/api/me/voice-settings").json()
    assert (body["voice_en"], body["voice_fil"], body["rate"], body["pitch"], body["volume"]) == (
        "en-PH-RosaNeural", "fil-PH-BlessicaNeural", -10, 0, 100)
    assert [v["name"] for v in body["voices"]["fil"]] == ["Blessica", "Angelo"]
    assert {v["id"] for v in body["voices"]["en"]} >= {"en-PH-JamesNeural", "en-US-JennyNeural", "en-US-GuyNeural"}
    say(api, "I need water")
    say(api, "Salamat", "fil")
    assert [(c[1], c[2], c[3]) for c in voice["calls"]] == [("en-PH-RosaNeural", -10, 0),
                                                           ("fil-PH-BlessicaNeural", -10, 0)]


def test_saved_settings_are_used_and_logged(api, ana, voice, test_database):
    body = api.put("/api/me/voice-settings", json={"voice_fil": "fil-PH-AngeloNeural", "rate": -25,
                                                   "pitch": 5}).json()
    assert (body["voice_fil"], body["rate"], body["pitch"], body["voice_en"]) == (
        "fil-PH-AngeloNeural", -25, 5, "en-PH-RosaNeural")
    say(api, "Oo", "fil")
    assert voice["calls"][-1][1:] == ("fil-PH-AngeloNeural", -25, 5)
    entry = logs(test_database, "voice_settings_changed")[0].activity_description
    assert entry == "Voice settings for Ana Cruz changed (Filipino voice Angelo, speed -25, pitch +5)"
    with test_database() as db:  # never touches the accessibility settings row
        assert db.scalars(select(AccessibilitySettings)).all() == []


def test_reset_to_default(api, ana, voice, test_database):
    api.put("/api/me/voice-settings", json={"voice_en": "en-US-GuyNeural", "rate": 20})
    body = api.post("/api/me/voice-settings/reset").json()
    assert (body["voice_en"], body["rate"]) == ("en-PH-RosaNeural", -10)
    assert len(logs(test_database, "voice_settings_reset")) == 1


def test_settings_keep_the_language_choice(api, ana, voice):
    api.put("/api/me/language", json={"language": "fil"})
    api.put("/api/me/voice-settings", json={"rate": 0})
    api.post("/api/me/voice-settings/reset")
    assert api.get("/api/me/language").json() == {"language": "fil"}


@pytest.mark.parametrize("body", [{"voice_en": "fil-PH-AngeloNeural"}, {"voice_fil": "en-PH-RosaNeural"},
                                  {"voice_en": "Microsoft David"}, {"rate": 80}, {"pitch": -50}])
def test_invalid_settings_are_refused(api, ana, voice, body):
    assert api.put("/api/me/voice-settings", json=body).status_code == 422


def test_preview_of_an_unsaved_choice(api, ana, voice):
    say(api, "Kumusta, ganito ang aking boses.", "fil", voice="fil-PH-AngeloNeural", rate=10, pitch=-5)
    assert voice["calls"][-1][1:] == ("fil-PH-AngeloNeural", 10, -5)
    assert say(api, "Hello", "en", voice="fil-PH-AngeloNeural").status_code == 422  # wrong language


# --- Speaking, cache, fallback -------------------------------------------------------------------

def test_neural_then_cache(api, ana, voice):
    first = say(api, "I need help").json()
    assert first["source"] == "neural" and first["boundaries"] == MARKS
    assert base64.b64decode(first["audio"]) == b"MP3:en-PH-RosaNeural:I need help"
    second = say(api, "I need help").json()
    assert second["source"] == "cache" and second["audio"] == first["audio"] and second["boundaries"] == MARKS
    assert len(voice["calls"]) == 1
    assert len(list(tts.cache_dir.glob("*.mp3"))) == 1


def test_cached_phrases_still_play_offline(api, ana, voice):
    say(api, "Thank you")
    voice["fail"] = True
    assert say(api, "Thank you").json()["source"] == "cache"
    response = say(api, "Something new")
    assert response.status_code == 503 and "could not be reached" in response.json()["detail"]
    assert len(list(tts.cache_dir.glob("*.mp3"))) == 1  # failures are never cached


def test_cache_is_per_voice_speed_and_pitch(api, ana, voice):
    say(api, "Yes")
    say(api, "Yes", rate=0)
    say(api, "Yes", voice="en-US-JennyNeural")
    assert len(voice["calls"]) == 3


def test_cache_size_limit_removes_the_oldest(api, ana, voice, monkeypatch):
    monkeypatch.setattr(tts, "CACHE_LIMIT_BYTES", 120)
    for n, text in enumerate(["one phrase", "two phrase", "three phrase"]):
        say(api, text)
        for f in tts.cache_dir.glob("*.mp3"):  # make the order of use clear to the file system
            if text.split()[0] not in f.read_bytes().decode():
                os.utime(f, (n, n))
    kept = sorted(f.read_bytes().decode() for f in tts.cache_dir.glob("*.mp3"))
    assert "MP3:en-PH-RosaNeural:one phrase" not in kept
    assert tts.cache_size_bytes() <= 120


def test_text_is_cleaned_before_speaking(api, ana, voice):
    body = say(api, "I need 3 pills at 3:30 PM!!!").json()
    assert voice["calls"][-1][0] == body["text"] == "I need three pills at three thirty P M!"


def test_filtered_words_are_never_sent_to_the_voice(api, ana, voice, test_database, monkeypatch, tmp_path):
    monkeypatch.setattr(word_filter_service, "SEED_FILE", tmp_path / "none.txt")
    word_filter_service.reset_process_state()
    with test_database() as db:
        db.add(FilteredWord(word="badword1", normalized_word=word_filter_service.normalize("badword1"),
                            language="en", type="blocked"))
        db.commit()
    word_filter_service.invalidate()
    say(api, "you b@dw0rd1 there")
    api.post("/api/tts/warm", json={"texts": ["hey badword1"], "language": "en"})
    word_filter_service.reset_process_state()
    assert [c[0] for c in voice["calls"]] == ["you beep there", "hey beep"]


@pytest.mark.parametrize("text", ["", "   ", "😀", "a. " * 400])
def test_nothing_to_say_or_too_long(api, ana, voice, text):
    assert say(api, text).status_code == 422
    assert voice["calls"] == []


def test_four_second_limit_on_the_first_audio(api, ana, monkeypatch, tmp_path):
    """The real engine wrapper with a fake edge-tts that never sends audio in time."""
    class SlowCommunicate:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def stream(self):
            await asyncio.sleep(5)
            yield {"type": "audio", "data": b"late"}

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=SlowCommunicate))
    monkeypatch.setattr(tts, "FIRST_AUDIO_TIMEOUT_S", 0.2)
    monkeypatch.setattr(tts, "cache_dir", tmp_path / "tts_cache")
    response = say(api, "Hello")
    assert response.status_code == 503


def test_real_engine_wrapper_collects_audio_and_word_timings(monkeypatch):
    seen = {}

    class FakeCommunicate:
        def __init__(self, text, voice_id, **kwargs):
            seen.update(text=text, voice=voice_id, **kwargs)

        async def stream(self):
            yield {"type": "WordBoundary", "offset": 1_000_000, "duration": 2_500_000, "text": "Hello"}
            yield {"type": "audio", "data": b"ab"}
            yield {"type": "audio", "data": b"cd"}

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=FakeCommunicate))
    audio, marks = tts._edge_engine("Hello", "en-PH-RosaNeural", -10, 5)
    assert audio == b"abcd" and marks == [{"offset_ms": 100, "duration_ms": 250, "text": "Hello"}]
    assert (seen["rate"], seen["pitch"], seen["boundary"]) == ("-10%", "+5Hz", "WordBoundary")


# --- Pre-generating Quick Phrases ----------------------------------------------------------------

def test_warm_saves_phrases_for_later(api, ana, voice):
    phrases = ["Tulungan mo ako", "Oo", "Hindi"]
    assert api.post("/api/tts/warm", json={"texts": phrases, "language": "fil"}).json() == {"started": True, "count": 3}
    assert [c[0] for c in voice["calls"]] == phrases
    voice["fail"] = True
    assert all(say(api, p, "fil").json()["source"] == "cache" for p in phrases)


def test_warm_stops_when_offline(api, ana, voice):
    voice["fail"] = True
    api.post("/api/tts/warm", json={"texts": ["a", "b", "c"], "language": "en"})
    assert voice["calls"] == []


def test_one_warm_job_at_a_time(api, ana, voice, monkeypatch):
    monkeypatch.setattr(tts, "_warming", {"en|en-PH-RosaNeural|-10|0"})
    assert api.post("/api/tts/warm", json={"texts": ["a"], "language": "en"}).json()["started"] is False


def test_too_many_warm_phrases(api, ana, voice):
    assert api.post("/api/tts/warm", json={"texts": ["x"] * 21, "language": "en"}).status_code == 422


# --- Access ----------------------------------------------------------------------------------------

def test_assistive_users_only(api, signed_in_admin, voice):
    assert signed_in_admin.post("/api/tts/speak", json={"text": "Hi"}).status_code == 403
    assert signed_in_admin.get("/api/me/voice-settings").status_code == 403
    signed_in_admin.post("/api/auth/logout")
    assert api.post("/api/tts/speak", json={"text": "Hi"}).status_code == 401
    assert voice["calls"] == []
