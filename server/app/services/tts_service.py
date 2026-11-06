"""Filipino voice fallback (extension): when the browser has no Filipino voice,
the site asks for an MP3 made by gTTS (Google Translate's voice, language
"tl"). It needs the internet; if Google cannot be reached the site says so
and never reads Filipino with an English voice.

The desktop guidance voice (pyttsx3) is separate and unchanged.
"""

import logging
import threading
from collections import OrderedDict
from io import BytesIO

logger = logging.getLogger("irisclick.tts")

MAX_CHARS = 500
CACHE_SIZE = 64
GTTS_LANG = {"fil": "tl"}
OFFLINE = ("The Filipino voice needs the internet, and it could not be reached. "
           "Check the connection and try again.")


class TtsError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _gtts(text: str, lang: str) -> bytes:
    from gtts import gTTS  # imported here so the server still starts without gTTS

    buffer = BytesIO()
    gTTS(text=text, lang=lang).write_to_fp(buffer)
    return buffer.getvalue()


engine = _gtts  # replaced in tests: never call Google from the test suite
_cache: OrderedDict[tuple[str, str], bytes] = OrderedDict()
_lock = threading.Lock()


def synthesize(text: str, language: str = "fil") -> bytes:
    """MP3 bytes for ``text``; raises TtsError with a message for the user."""
    text = " ".join((text or "").split())
    if not text:
        raise TtsError(422, "There is nothing to say.")
    if len(text) > MAX_CHARS:
        raise TtsError(422, f"The Filipino voice can read up to {MAX_CHARS} characters at a time.")
    lang = GTTS_LANG.get(language)
    if lang is None:
        raise TtsError(422, "Only Filipino uses this voice.")
    key = (lang, text)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    try:
        audio = engine(text, lang)
    except ImportError as exc:
        logger.exception("gTTS is not installed")
        raise TtsError(503, "The Filipino voice is not installed on this computer.") from exc
    except Exception as exc:  # noqa: BLE001 - gTTSError, requests errors, timeouts
        logger.warning("Filipino voice failed: %s", exc)
        raise TtsError(503, OFFLINE) from exc
    if not audio:
        raise TtsError(503, OFFLINE)
    with _lock:
        _cache[key] = audio
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return audio


def clear_cache() -> None:
    with _lock:
        _cache.clear()
