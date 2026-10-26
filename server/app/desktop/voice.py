"""Offline spoken guidance (Windows SAPI5 via pyttsx3).

pyttsx3's runAndWait blocks and its COM engine is bound to the thread that
created it, so one daemon thread owns the engine and speaks queued lines.
"""

import logging
import queue
import threading

logger = logging.getLogger("irisclick.voice")

# Matches the desktop app's guidance pacing: at most ~150 words per minute.
WORDS_PER_MINUTE = 150


class Speaker:
    def __init__(self):
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="voice", daemon=True)
        self.available = True

    def start(self):
        self._thread.start()

    def say(self, text: str):
        # Only the newest instruction matters; drop anything not yet spoken.
        while not self._lines.empty():
            self._lines.get_nowait()
        self._lines.put(text)

    def stop(self):
        self._lines.put(None)

    def _run(self):
        try:
            import comtypes
            import pyttsx3

            comtypes.CoInitialize()
            engine = pyttsx3.init()
            engine.setProperty("rate", WORDS_PER_MINUTE)
        except Exception as exc:
            self.available = False
            logger.warning("Voice guidance unavailable: %s", exc)
            return
        while (line := self._lines.get()) is not None:
            try:
                engine.say(line)
                engine.runAndWait()
            except Exception as exc:
                logger.warning("Voice line failed: %s", exc)


class VoiceGuide:
    """Speaks a warning only once it persists, and never nags.

    ``observe`` is called every tick with the current problem (or None). A
    problem must last ``persist_s`` before it is spoken (ordinary blinks and
    one-frame dropouts stay silent); the same line waits ``repeat_s`` before
    repeating, and any two lines are ``gap_s`` apart.
    """

    def __init__(self, speaker: Speaker, persist_s=1.5, repeat_s=25.0, gap_s=6.0):
        self.speaker = speaker
        self.enabled = True
        self.persist_s = persist_s
        self.repeat_s = repeat_s
        self.gap_s = gap_s
        self._key = None
        self._since = 0.0
        self._last_spoken: dict[str, float] = {}
        self._last_any = float("-inf")

    def observe(self, key: str | None, text: str | None, now: float):
        if key is None or text is None:
            self._key = None
            return
        if key != self._key:
            self._key, self._since = key, now
            return
        if (not self.enabled or now - self._since < self.persist_s
                or now - self._last_spoken.get(key, float("-inf")) < self.repeat_s
                or now - self._last_any < self.gap_s):
            return
        self._last_spoken[key] = self._last_any = now
        self.speaker.say(text)

    def announce(self, text: str, now: float):
        """Speak an event (pause, resume) right away."""
        if self.enabled:
            self._last_any = now
            self.speaker.say(text)
