"""Panel revision: valid-data identification, "Go to Facebook" and voice typing.

No microphone is used: recognition results are fed in as Heard tuples, and typed
keys are captured instead of sent to Windows.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.voice import commands as cmd
from app.voice import shortcuts
from app.voice.controller import TYPING_IDLE_S, VoiceController
from app.voice.recognizer import Heard, choose_microphone
from app.voice.typing import VK_CONTROL, VK_DELETE, VK_RETURN, VK_SHIFT, VoiceTyper, text_events

SITE = "https://iris-click.example.app"
EVIL = "https://evil.example.com"


@pytest.fixture
def shortcut_file(tmp_path, monkeypatch):
    path = tmp_path / "voice_shortcuts.json"
    monkeypatch.setattr(shortcuts, "SHORTCUTS_PATH", path)
    return path


def names(path=None):
    return frozenset(shortcuts.directory(path) if path else shortcuts.directory())


# --- Classifier: valid navigation / valid action / dictation / invalid ---------------------------

@pytest.mark.parametrize("spoken", ["Go to Facebook", "go to facebook", "Open Facebook.", "Please go to Facebook",
                                    "go to the facebook website", "visit facebook.com", "Launch FACEBOOK!"])
def test_go_to_facebook_is_a_valid_navigation_command(spoken, shortcut_file):
    result = cmd.classify(spoken, 0.9, False, names(shortcut_file))
    assert result.kind == cmd.NAVIGATE and result.valid
    assert shortcuts.directory(shortcut_file)[result.name].value == "https://www.facebook.com"


@pytest.mark.parametrize("spoken,site", [("Go to YouTube", "youtube"), ("Open Google", "google"),
                                         ("go to messenger", "messenger"), ("open gmail", "gmail")])
def test_built_in_sites(spoken, site, shortcut_file):
    result = cmd.classify(spoken, 0.9, False, names(shortcut_file))
    assert (result.kind, result.name) == (cmd.NAVIGATE, site)


@pytest.mark.parametrize("spoken,reason", [
    ("", "No speech heard"), ("   ", "No speech heard"), ("!!!", "No speech heard"),
    ("Go to Netflix", 'No website or app called "netflix"'),
    ("what is the weather", "Unrecognized command"),
    ("send", 'Say "Start typing" first'),
    ("go to javascript:alert(1)", 'No website or app called "javascript alert 1"'),
])
def test_invalid_input_is_rejected_with_a_reason(spoken, reason, shortcut_file):
    result = cmd.classify(spoken, 0.9, False, names(shortcut_file))
    assert result.kind == cmd.INVALID and not result.valid
    assert result.reason == reason


def test_low_confidence_is_never_guessed(shortcut_file):
    result = cmd.classify("go to facebook", 0.2, False, names(shortcut_file))
    assert result.kind == cmd.INVALID and "Not sure" in result.reason


@pytest.mark.parametrize("spoken,action", [("Start typing", cmd.START_TYPING), ("type message", cmd.START_TYPING)])
def test_start_typing_is_a_valid_action(spoken, action):
    assert cmd.classify(spoken).action == action


@pytest.mark.parametrize("spoken,action", [("Send", cmd.SEND), ("press enter", cmd.SEND), ("Clear", cmd.CLEAR),
                                           ("new line", cmd.NEW_LINE), ("Stop typing", cmd.STOP_TYPING)])
def test_typing_actions_only_while_typing(spoken, action):
    assert cmd.classify(spoken, typing=True).action == action


def test_speech_while_typing_is_dictation_and_keeps_its_case():
    result = cmd.classify("Hi I'm Knoxville", 0.6, typing=True)
    assert result.kind == cmd.DICTATION and result.text == "Hi I'm Knoxville"


def test_go_to_facebook_while_typing_is_typed_not_opened():
    assert cmd.classify("go to facebook", typing=True, known_names=frozenset({"facebook"})).kind == cmd.DICTATION


def test_dictation_rejects_noise_and_strips_control_characters():
    assert cmd.classify("...", typing=True).kind == cmd.INVALID
    assert cmd.classify("hello\x00 there\x1b", typing=True).text == "hello there"
    assert len(cmd.classify("a" * 900, typing=True).text) == cmd.MAX_DICTATION_CHARS


def test_command_phrases_include_go_to_for_every_name():
    phrases = cmd.command_phrases({"facebook", "my school"})
    assert {"go to facebook", "open my school", "start typing", "send", "stop typing"} <= set(phrases)


# --- Shortcuts: only valid http/https addresses ------------------------------------------------

def test_saved_tiles_add_go_to_names_and_bad_addresses_are_dropped(shortcut_file):
    kept, rejected = shortcuts.save([
        {"label": "My School", "url": "https://uc.edu.ph"},
        {"label": "Bad", "url": "javascript:alert(1)"},
        {"label": "Spaces", "url": "https://bad site.com"},
        {"label": "Hidden user", "url": "https://bank.com@evil.com"},
        {"label": "", "url": "https://empty-label.com"},
        {"label": "Typed", "url": "example.com"},
    ], shortcut_file)
    assert (kept, rejected) == (2, 4)
    found = shortcuts.directory(shortcut_file)
    assert found["my school"].value == "https://uc.edu.ph"
    assert found["example"].value == "https://example.com"
    assert cmd.classify("go to my school", known_names=frozenset(found)).kind == cmd.NAVIGATE


def test_a_tampered_file_never_yields_an_invalid_address(shortcut_file):
    shortcut_file.write_text(json.dumps([{"label": "Evil", "url": "file:///C:/Windows"}, "junk", 5]))
    assert shortcuts.load_saved(shortcut_file) == []
    shortcut_file.write_text("not json")
    assert shortcuts.load_saved(shortcut_file) == []


# --- Voice typing: real key presses into the focused text box ----------------------------------

def test_typing_sends_unicode_characters_with_spaces_between_phrases():
    sent = []
    typer = VoiceTyper(send_events=sent.append)
    typer.type_text("Hi I'm Knoxville")
    typer.type_text("Kumusta ka? ñ")
    typed = "".join(e[1] for batch in sent for e in batch if e[0] == "char")
    assert typed == "Hi I'm Knoxville Kumusta ka? ñ"


def test_send_clear_and_new_line_keys():
    sent = []
    typer = VoiceTyper(send_events=sent.append)
    typer.send()
    typer.clear()
    typer.new_line()
    assert sent[0] == [("key", VK_RETURN, False), ("key", VK_RETURN, True)]
    assert sent[1][:4] == [("key", VK_CONTROL, False), ("key", ord("A"), False), ("key", ord("A"), True),
                           ("key", VK_CONTROL, True)]
    assert ("key", VK_DELETE, False) in sent[1]
    assert sent[2] == [("key", VK_SHIFT, False), ("key", VK_RETURN, False), ("key", VK_RETURN, True),
                       ("key", VK_SHIFT, True)]


def test_a_newline_in_text_never_sends_the_message():
    assert ("key", VK_RETURN, False) in text_events("a\nb")
    assert text_events("a\nb")[1] == ("key", VK_SHIFT, False)


# --- Controller: the whole flow, with fakes ---------------------------------------------------

class FakeRecognizer:
    def __init__(self, on_heard, on_error):
        self.on_heard, self.on_error = on_heard, on_error
        self.started, self.typing = False, False

    def start(self, phrases):
        self.started, self.phrases = True, phrases

    def stop(self):
        self.started = False

    def set_typing(self, typing):
        self.typing = typing


@pytest.fixture
def voice(shortcut_file):
    log = {"feedback": [], "urls": [], "apps": [], "keys": [], "state": []}
    clock = {"t": 0.0}
    controller = VoiceController(
        feedback=lambda text, ok: log["feedback"].append((text, ok)),
        on_state=lambda listening, typing: log["state"].append((listening, typing)),
        open_url=log["urls"].append, open_app=log["apps"].append,
        typer=VoiceTyper(send_events=log["keys"].append),
        directory=lambda: shortcuts.directory(shortcut_file),
        recognizer_factory=FakeRecognizer, clock=lambda: clock["t"])
    return controller, log, clock


def say(controller, text, confidence=0.9):
    controller._recognizer.on_heard(Heard(text, confidence, True))
    controller.process_pending()


def test_mic_is_off_until_turned_on_and_shows_its_state(voice):
    controller, log, _ = voice
    say(controller, "go to facebook")
    assert log["urls"] == []  # heard while off: ignored
    assert controller.toggle() is True and controller._recognizer.started
    assert log["state"][-1] == (True, False)
    assert controller.toggle() is False and not controller._recognizer.started
    assert log["state"][-1] == (False, False)


def test_go_to_facebook_opens_facebook_with_green_feedback(voice):
    controller, log, _ = voice
    controller.toggle()
    say(controller, "Go to Facebook")
    assert log["urls"] == ["https://www.facebook.com"]
    assert log["feedback"][-1] == ("\u2714 Valid command: Opening Facebook", True)


def test_unrecognized_speech_does_nothing_and_shows_red_feedback(voice):
    controller, log, _ = voice
    controller.toggle()
    for spoken in ("go to netflix", "what is the weather", "", "go to facebook"):
        say(controller, spoken, confidence=0.9 if spoken != "go to facebook" else 0.1)
    assert log["urls"] == [] and log["apps"] == [] and log["keys"] == []
    assert all(ok is False for _, ok in log["feedback"][1:])
    assert all(text.startswith("\u2716 Unrecognized / invalid input") for text, _ in log["feedback"][1:])


def test_start_typing_dictation_send_and_stop(voice):
    controller, log, _ = voice
    controller.toggle()
    say(controller, "Start typing")
    assert controller.typing and controller._recognizer.typing
    say(controller, "Hi I'm Knoxville", 0.6)
    say(controller, "Send")
    say(controller, "Stop typing")
    typed = "".join(e[1] for batch in log["keys"] for e in batch if e[0] == "char")
    assert typed == "Hi I'm Knoxville"
    assert ("key", VK_RETURN, False) in log["keys"][-1]
    assert not controller.typing and log["state"][-1] == (True, False)


def test_voice_typing_switches_itself_off_after_a_quiet_minute(voice):
    controller, log, clock = voice
    controller.toggle()
    say(controller, "start typing")
    clock["t"] = TYPING_IDLE_S + 1
    controller.process_pending()
    assert not controller.typing
    assert "no speech for a minute" in log["feedback"][-1][0]


def test_stop_typing_button_and_mic_off_end_typing(voice):
    controller, _, _ = voice
    controller.toggle()
    say(controller, "start typing")
    controller.stop_typing()
    assert not controller.typing and controller.listening
    say(controller, "start typing")
    controller.toggle()
    assert not controller.typing and not controller.listening


def test_a_recogniser_error_turns_the_mic_off(voice):
    controller, log, _ = voice
    controller.toggle()
    controller._recognizer.on_error("No microphone was found.")
    controller.process_pending()
    assert not controller.listening
    assert log["feedback"][-1] == ("\u2716 No microphone was found.", False)


def test_app_names_open_the_fixed_app_list(voice):
    controller, log, _ = voice
    controller.toggle()
    say(controller, "open calculator")
    assert log["apps"] == ["calculator"] and log["urls"] == []


def test_logs_never_contain_what_was_said(voice, caplog):
    controller, _, _ = voice
    controller.toggle()
    with caplog.at_level("INFO", logger="irisclick.voice"):
        say(controller, "start typing")
        say(controller, "my secret message", 0.6)
    assert "secret" not in caplog.text and "dictation" in caplog.text


def test_microphone_choice_prefers_a_real_microphone():
    names = ["Voicemeeter Out B3", "Microphone Array (Intel)", "Headset"]
    assert choose_microphone(names, None) == 1
    assert choose_microphone(names, "headset") == 2
    assert choose_microphone(["Line In"], None) == 0


# --- Local routes: origin-guarded, checked addresses -----------------------------------------

@pytest.fixture
def client(monkeypatch, shortcut_file):
    from app.api import main
    settings = get_settings().model_copy(update={"cors_origins": [SITE]})
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    return TestClient(main.create_app())


def test_voice_check_route_classifies_like_the_microphone(client):
    ok = client.post("/api/desktop/voice-check", json={"text": "Go to Facebook"}, headers={"Origin": SITE}).json()
    assert ok["valid"] and ok["kind"] == "navigate"
    bad = client.post("/api/desktop/voice-check", json={"text": "Go to Netflix"}, headers={"Origin": SITE}).json()
    assert not bad["valid"] and bad["kind"] == "invalid"
    typed = client.post("/api/desktop/voice-check", json={"text": "Hi I'm Knoxville", "typing": True},
                        headers={"Origin": SITE}).json()
    assert typed["kind"] == "dictation"


def test_shortcuts_route_keeps_only_valid_addresses(client, shortcut_file):
    body = {"shortcuts": [{"label": "UC", "url": "https://uc.edu.ph"}, {"label": "X", "url": "ftp://files.example.com"}]}
    saved = client.put("/api/desktop/voice-shortcuts", json=body, headers={"Origin": SITE}).json()
    assert saved == {"saved": 1, "rejected": 1}
    listed = client.get("/api/desktop/voice-shortcuts", headers={"Origin": SITE}).json()
    assert "uc" in listed["names"] and "facebook" in listed["names"]


def test_other_websites_cannot_use_the_voice_routes(client):
    assert client.post("/api/desktop/voice-check", json={"text": "go to facebook"},
                       headers={"Origin": EVIL}).status_code == 403
    assert client.put("/api/desktop/voice-shortcuts", json={"shortcuts": []},
                      headers={"Origin": EVIL}).status_code == 403
