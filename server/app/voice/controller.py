"""Voice commands and voice typing inside the tracking worker.

The recogniser thread only queues what it heard; ``process_pending`` runs on the
worker's Tk thread, classifies each phrase (commands.classify) and acts:

  NAVIGATE   open the checked website in the browser, or launch the built-in app
  ACTION     start/stop voice typing, Send (Enter), Clear, New line
  DICTATION  type the words into the focused text box (typing.VoiceTyper)
  INVALID    nothing happens

Every phrase gets on-screen feedback: green "✔ Valid command: ..." or red
"✖ Unrecognized / invalid input: ...". Logs record only the kind of input and
its length, never the words (they can be private).
"""

import logging
import queue
import time
import webbrowser
from collections.abc import Callable

from app.voice import commands as cmd
from app.voice import shortcuts
from app.voice.recognizer import Heard, Recognizer
from app.voice.typing import VoiceTyper

logger = logging.getLogger("irisclick.voice")

# Voice typing switches itself off after this long without speech, so it can never get stuck on.
TYPING_IDLE_S = 60.0
MIC_ON = "Microphone on: say “Go to Facebook” or “Start typing”"


def open_website(url: str) -> None:
    webbrowser.open(url, new=2)


def launch_app(app_id: str) -> None:
    from app.services import apps_service

    apps_service.launch(app_id)


class VoiceController:
    def __init__(self, feedback: Callable[[str, bool | None], None],
                 on_state: Callable[[bool, bool], None] = lambda listening, typing: None,
                 open_url: Callable[[str], None] = open_website,
                 open_app: Callable[[str], None] = launch_app,
                 typer: VoiceTyper | None = None,
                 directory: Callable[[], dict] = shortcuts.directory,
                 recognizer_factory: Callable[..., Recognizer] = Recognizer,
                 clock: Callable[[], float] = time.monotonic):
        self._feedback = feedback
        self._on_state = on_state
        self._open_url, self._open_app = open_url, open_app
        self.typer = typer or VoiceTyper()
        self._directory = directory
        self._recognizer = recognizer_factory(self._heard, self._error)
        self._clock = clock
        self._pending: queue.Queue[Heard | str] = queue.Queue()
        self.listening = False
        self.typing = False
        self._last_speech = 0.0
        self._targets: dict = {}

    # ---- called from any thread ---------------------------------------------------------

    def _heard(self, heard: Heard) -> None:
        self._pending.put(heard)

    def _error(self, text: str) -> None:
        self._pending.put(text)

    # ---- Tk thread ---------------------------------------------------------------------

    def toggle(self) -> bool:
        """Mic on/off (control bar). Off also ends voice typing."""
        if self.listening:
            self.stop()
            self._feedback("Microphone off", None)
        else:
            self._targets = self._directory()
            self._recognizer.start(cmd.command_phrases(set(self._targets)))
            self.listening = True
            self._last_speech = self._clock()
            self._feedback(MIC_ON, None)
            logger.info("Voice commands on")
        self._state_changed()
        return self.listening

    def stop(self) -> None:
        self._recognizer.stop()
        self.listening = False
        self._set_typing(False)
        logger.info("Voice commands off")
        self._state_changed()

    def stop_typing(self) -> None:
        """The control bar's way out of voice typing, for when "Stop typing" is not heard."""
        if self.typing:
            self._set_typing(False)
            self._feedback("✔ Voice typing off", True)
            self._state_changed()

    def process_pending(self) -> None:
        while True:
            try:
                item = self._pending.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, str):  # recogniser error: say it once and turn the mic off
                self._feedback(f"✖ {item}", False)
                self.listening = False
                self._set_typing(False)
                self._state_changed()
            elif self.listening:
                self.handle(item)
        if self.typing and self._clock() - self._last_speech > TYPING_IDLE_S:
            self._set_typing(False)
            self._feedback("Voice typing off (no speech for a minute)", None)
            self._state_changed()

    def handle(self, heard: Heard) -> cmd.Classified:
        result = cmd.classify(heard.text, heard.confidence, self.typing, frozenset(self._targets))
        logger.info("Voice input: %s (%s, %d chars)", result.kind, result.action or "-", len(heard.text or ""))
        if result.kind != cmd.INVALID:
            self._last_speech = self._clock()
        if result.kind == cmd.INVALID:
            self._feedback(f"✖ Unrecognized / invalid input: {result.reason}", False)
        elif result.kind == cmd.NAVIGATE:
            self._navigate(result)
        elif result.kind == cmd.ACTION:
            self._act(result)
        else:  # DICTATION
            self.typer.type_text(result.text or "")
            self._feedback(f"✔ {result.reason}", True)
        return result

    def _navigate(self, result: cmd.Classified) -> None:
        target = self._targets.get(result.name or "")
        if target is None:
            self._feedback(f'✖ Unrecognized / invalid input: No website or app called "{result.name}"', False)
            return
        try:
            if target.kind == shortcuts.WEBSITE:
                url = shortcuts.valid_url(target.value)
                if url is None:  # never open an address that fails the check
                    self._feedback("✖ Invalid website address: not opened", False)
                    return
                self._open_url(url)
            else:
                self._open_app(target.value)
        except Exception as exc:  # noqa: BLE001 - an app that is not installed, for example
            self._feedback(f"✖ Could not open {target.label}: {getattr(exc, 'message', 'not available')}", False)
            return
        self._feedback(f"✔ Valid command: Opening {target.label}", True)

    def _act(self, result: cmd.Classified) -> None:
        action = result.action
        if action == cmd.START_TYPING:
            self._set_typing(True)
            self._feedback("✔ Valid command: Voice typing on. Click a text box, then speak", True)
        elif action == cmd.STOP_TYPING:
            self._set_typing(False)
            self._feedback("✔ Valid command: Voice typing off", True)
        elif action == cmd.SEND:
            self.typer.send()
            self._feedback("✔ Valid command: Sent (Enter)", True)
        elif action == cmd.CLEAR:
            self.typer.clear()
            self._feedback("✔ Valid command: Message cleared", True)
        elif action == cmd.NEW_LINE:
            self.typer.new_line()
            self._feedback("✔ Valid command: New line", True)
        self._state_changed()

    def _set_typing(self, typing: bool) -> None:
        if typing == self.typing:
            return
        self.typing = typing
        self.typer.reset()
        self._recognizer.set_typing(typing)
        self._last_speech = self._clock()

    def _state_changed(self) -> None:
        self._on_state(self.listening, self.typing)
