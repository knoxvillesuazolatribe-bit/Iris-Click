"""Offline speech recognition with Windows' own recogniser (SAPI 5, English - US).

Two grammars run together on one in-process recogniser:
  * a command grammar with every exact command phrase ("go to facebook", "send", ...),
    which makes commands easy to hear correctly;
  * free dictation, switched on only while voice typing is on, for the words to type.
In command mode a phrase that is not a command comes back as a low-confidence match
or a false recognition, which the classifier marks "Unrecognized".

Recognition runs on its own thread (SAPI events need a COM message loop there) and
each result is handed to ``on_heard`` as a Heard tuple. Audio stays inside Windows:
nothing is recorded, saved or sent. Needs comtypes (already installed with pyttsx3).
"""

import logging
import os
import threading
from collections.abc import Callable
from typing import NamedTuple

logger = logging.getLogger("irisclick.voice.recognizer")

SGDSInactive, SGDSActive = 0, 1
SRATopLevel, SRADynamic = 1, 32
SGLexical = 1
CMD_GRAMMAR, DICTATION_GRAMMAR = 1, 2
# SAPI's confidence classes (SpeechEngineConfidence) mapped onto 0..1 for the classifier.
CONFIDENCE = {-1: 0.2, 0: 0.6, 1: 0.9}
MIC_ENV = "VOICE_MIC"
# Microsoft Speech Object Library 5.4 (sapi.dll), by type-library id so no path is needed.
SAPI_TYPELIB = ("{C866CA3A-32F7-11D2-9602-00C04F8EE628}", 5, 4)


class Heard(NamedTuple):
    text: str
    confidence: float
    from_commands: bool


def choose_microphone(names: list[str], wanted: str | None) -> int:
    """VOICE_MIC (part of a device name) if set, else a real microphone, else the first device."""
    lowered = [n.lower() for n in names]
    if wanted:
        for i, name in enumerate(lowered):
            if wanted.lower() in name:
                return i
    for i, name in enumerate(lowered):
        if "microphone" in name or "mic " in name:
            return i
    return 0


def pump_messages() -> None:
    """SAPI posts its events as window messages to this thread: dispatch whatever is waiting."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    msg = wintypes.MSG()
    while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):  # PM_REMOVE
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


class Recognizer:
    def __init__(self, on_heard: Callable[[Heard], None], on_error: Callable[[str], None] | None = None,
                 audio_file: str | None = None):
        self._audio_file = audio_file  # tests and checks only: a WAV file instead of the microphone
        self._on_heard = on_heard
        self._on_error = on_error or (lambda text: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._typing = False
        self._phrases: list[str] = []
        self._phrases_dirty = threading.Event()
        self._typing_dirty = threading.Event()
        self.microphone = ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, phrases: list[str]) -> None:
        if self.running and self._stop.is_set():  # switched off a moment ago: let it finish first
            self._thread.join(2.0)
        if self.running:
            self.set_phrases(phrases)
            return
        self._phrases = list(phrases)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="irisclick-voice", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def set_typing(self, typing: bool) -> None:
        with self._lock:
            self._typing = typing
        self._typing_dirty.set()

    def set_phrases(self, phrases: list[str]) -> None:
        with self._lock:
            self._phrases = list(phrases)
        self._phrases_dirty.set()

    # ---- recogniser thread -------------------------------------------------------------

    def _run(self) -> None:
        try:
            import comtypes
            import comtypes.client as cc
        except ImportError:
            self._on_error("Voice commands need Windows speech recognition, which is not available.")
            return
        comtypes.CoInitialize()
        try:
            recognizer = cc.CreateObject("SAPI.SpInprocRecognizer")
            if self._audio_file:
                stream = cc.CreateObject("SAPI.SpFileStream")
                stream.Open(self._audio_file, 0, False)  # SSFMOpenForRead
                recognizer.AudioInputStream = stream
                self.microphone = "file"
            else:
                inputs = recognizer.GetAudioInputs()
                names = [inputs.Item(i).GetDescription() for i in range(inputs.Count)]
                if not names:
                    self._on_error("No microphone was found.")
                    return
                index = choose_microphone(names, os.environ.get(MIC_ENV))
                recognizer.AudioInput = inputs.Item(index)
                self.microphone = names[index]
            context = recognizer.CreateRecoContext()
            commands = context.CreateGrammar(CMD_GRAMMAR)
            dictation = context.CreateGrammar(DICTATION_GRAMMAR)
            dictation.DictationLoad("", 0)
            self._phrases_dirty.clear()
            self._typing_dirty.clear()
            self._apply_typing(dictation)
            self._load_commands(commands)

            outer = self

            class Sink:
                def _ISpeechRecoContextEvents_Recognition(self, _stream, _position, _kind, result):
                    outer._deliver(result)

                def _ISpeechRecoContextEvents_FalseRecognition(self, _stream, _position, _result):
                    outer._on_heard(Heard("", 0.0, False))

            speech_lib = cc.GetModule(SAPI_TYPELIB)  # typed SAPI interfaces (cached by comtypes)
            connection = cc.GetEvents(context, Sink(), interface=speech_lib._ISpeechRecoContextEvents)
            logger.info("Voice recogniser listening on %s", self.microphone)
            while not self._stop.is_set():
                if self._phrases_dirty.is_set():  # new shortcuts: reload the command phrases
                    self._phrases_dirty.clear()
                    self._load_commands(commands)
                if self._typing_dirty.is_set():  # typing on/off: dictation first, then the commands
                    self._typing_dirty.clear()  # (the same order as at start; the other order left
                    self._apply_typing(dictation)  # dictation deaf in tests)
                    self._load_commands(commands)
                pump_messages()
                self._stop.wait(0.05)
            del connection
            dictation.DictationSetState(SGDSInactive)
            commands.CmdSetRuleState("commands", SGDSInactive)
        except Exception as exc:  # noqa: BLE001 - voice is an add-on: never stop eye tracking
            logger.exception("Voice recogniser stopped")
            self._on_error(f"Voice commands stopped: {type(exc).__name__}")
        finally:
            comtypes.CoUninitialize()

    def _apply_typing(self, dictation) -> None:
        """Free dictation only while voice typing is on: in command mode it would out-shout the
        exact command phrases ("face book" instead of "facebook")."""
        with self._lock:
            typing = self._typing
        dictation.DictationSetState(SGDSActive if typing else SGDSInactive)

    def _load_commands(self, grammar) -> None:
        with self._lock:
            phrases = list(self._phrases)
        rule = None
        if grammar.Rules.Count:
            rule = grammar.Rules.FindRule("commands")
        if not rule:
            rule = grammar.Rules.Add("commands", SRATopLevel | SRADynamic, 0)
        else:
            grammar.CmdSetRuleState("commands", SGDSInactive)
        rule.Clear()
        for phrase in phrases:
            rule.InitialState.AddWordTransition(None, phrase, " ", SGLexical, "", 0, None, 1.0)
        grammar.Rules.Commit()
        grammar.CmdSetRuleState("commands", SGDSActive)

    def _deliver(self, result) -> None:
        try:
            info = result.PhraseInfo
            text = info.GetText(0, -1, True)
            confidence = CONFIDENCE.get(int(info.Rule.Confidence), 0.6)
            from_commands = int(info.GrammarId) == CMD_GRAMMAR
            if from_commands:
                confidence = max(confidence, 0.6)  # an exact command phrase matched in full
            self._on_heard(Heard(text or "", confidence, from_commands))
        except Exception:  # noqa: BLE001
            logger.exception("Could not read a recognition result")
