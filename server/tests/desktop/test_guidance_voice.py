"""Guidance voice (clearer TTS, option F): saved natural voice first, pyttsx3 as before otherwise."""

import sys
import types

import pytest

from app.desktop import voice
from app.services import guidance_voice as gv
from app.services import neural_tts_service as tts


@pytest.fixture
def natural(monkeypatch, tmp_path):
    """Fake neural engine and MP3 player; background jobs run inline."""
    state = {"made": [], "played": [], "offline": False, "player_ok": True}

    def engine(text, voice_id, rate, pitch):
        if state["offline"]:
            raise ConnectionError("offline")
        state["made"].append(text)
        return b"MP3", []

    def player(path):
        state["played"].append(path.name)
        return state["player_ok"]

    monkeypatch.setattr(tts, "engine", engine)
    monkeypatch.setattr(tts, "cache_dir", tmp_path / "tts_cache")
    monkeypatch.setattr(gv, "runner", lambda fn: fn())
    monkeypatch.setattr(gv, "player", player)
    gv._pending.clear()
    return state


def test_first_time_pyttsx3_speaks_and_the_line_is_prepared(natural):
    assert gv.play_cached("Eye tracking is on.") is False   # pyttsx3 says it this time
    assert natural["made"] == ["Eye tracking is on."]
    assert gv.play_cached("Eye tracking is on.") is True    # natural voice from now on
    assert natural["played"] == [gv.cached_file("Eye tracking is on.").name]


def test_uses_the_default_english_voice_and_clear_speed(natural, monkeypatch):
    seen = []
    monkeypatch.setattr(tts, "engine", lambda text, v, r, p: seen.append((v, r, p)) or (b"MP3", []))
    gv.play_cached("Tracking resumed.")
    assert seen == [("en-PH-RosaNeural", -10, 0)]


def test_offline_never_fails_and_never_blocks(natural):
    natural["offline"] = True
    assert gv.play_cached("Tracking resumed.") is False
    assert gv.play_cached("Tracking resumed.") is False
    assert natural["played"] == []


def test_player_problem_falls_back_to_pyttsx3(natural):
    gv.play_cached("Voice guidance on.")
    natural["player_ok"] = False
    assert gv.play_cached("Voice guidance on.") is False


def test_known_lines_include_the_workers_guidance(natural, monkeypatch):
    fake_worker = types.SimpleNamespace(SPEECH={"no_face": "I cannot see your face."},
                                        POSTURE_SPEECH="You are sitting differently.")
    monkeypatch.setitem(sys.modules, "__main__", fake_worker)  # the worker runs with -m
    lines = gv.known_lines()
    assert {"Eye tracking is on.", "I cannot see your face.", "You are sitting differently."} <= set(lines)
    assert any("too dark" in line for line in lines) and any("closer" in line for line in lines)
    gv.prepare_known_lines()
    assert set(natural["made"]) == {gv.tts_text_prep.prepare(line, "en") for line in lines}
    natural["made"].clear()
    gv.prepare_known_lines()  # already saved: nothing made again
    assert natural["made"] == []


def test_windows_player_commands(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(gv.sys, "platform", "win32")
    monkeypatch.setattr(gv, "_mci", lambda command: sent.append(command) or 0)
    assert gv._play_mp3(tmp_path / "a.mp3") is True
    assert sent[0].startswith('open "') and "type mpegvideo alias irisclick_guide_" in sent[0]
    assert sent[1].endswith(" wait") and sent[2].startswith("close ")


def test_windows_player_reports_a_file_it_cannot_open(monkeypatch, tmp_path):
    monkeypatch.setattr(gv.sys, "platform", "win32")
    monkeypatch.setattr(gv, "_mci", lambda command: 263)  # MCI error code
    assert gv._play_mp3(tmp_path / "missing.mp3") is False


# --- The hook inside the existing Speaker (pyttsx3) --------------------------------------------

@pytest.fixture
def fake_pyttsx3(monkeypatch):
    said = []

    class Engine:
        def setProperty(self, *_args):
            pass

        def say(self, text):
            said.append(text)

        def runAndWait(self):
            pass

    monkeypatch.setitem(sys.modules, "pyttsx3", types.SimpleNamespace(init=lambda: Engine()))
    monkeypatch.setitem(sys.modules, "comtypes", types.SimpleNamespace(CoInitialize=lambda: None))
    return said


def run_speaker(*lines):
    speaker = voice.Speaker()
    for line in lines:
        speaker._lines.put(line)
    speaker._lines.put(None)
    speaker._run()


def test_speaker_uses_the_natural_voice_when_saved(natural, fake_pyttsx3):
    gv.play_cached("Tracking resumed.")  # prepare it
    natural["played"].clear()
    run_speaker("Tracking resumed.")
    assert fake_pyttsx3 == [] and len(natural["played"]) == 1


def test_speaker_falls_back_to_pyttsx3_when_not_saved(natural, fake_pyttsx3):
    natural["offline"] = True
    run_speaker("Tracking paused. Choose Resume to continue.")
    assert fake_pyttsx3 == ["Tracking paused. Choose Resume to continue."]


def test_speaker_still_works_if_the_natural_voice_breaks(fake_pyttsx3, monkeypatch):
    def broken(_line):
        raise RuntimeError("bug")

    monkeypatch.setattr(gv, "play_cached", broken)
    run_speaker("Eye tracking is on.")
    assert fake_pyttsx3 == ["Eye tracking is on."]
