"""Natural voice for the desktop guidance lines (clearer TTS, option F).

The tracking worker's Speaker (app/desktop/voice.py, pyttsx3) asks here first.
If the line's natural-voice audio is already saved on this computer, it is
played with Windows' own MP3 player (winmm MCI, no extra package) and pyttsx3
stays quiet. Otherwise this returns False, pyttsx3 speaks exactly as before,
and the line is prepared in the background so it sounds natural next time.

Guidance is English: the default natural English voice (Philippine English,
Rosa) at the clearer default speed. Nothing here ever blocks the worker when
offline: preparing runs in a background thread and stops at the first failure.
"""

import ctypes
import logging
import sys
import threading
from pathlib import Path

from app.services import neural_tts_service as tts
from app.services import tts_text_prep

logger = logging.getLogger("irisclick.guidance_voice")

LANGUAGE = "en"
VOICE = tts.DEFAULT_VOICE[LANGUAGE]
RATE = tts.DEFAULT_RATE
PITCH = tts.DEFAULT_PITCH
FIXED_LINES = ["Eye tracking is on.", "Tracking resumed.", "Voice guidance on."]

_pending: set[str] = set()
_lock = threading.Lock()
_counter = 0


def cached_file(text: str) -> Path:
    key = tts.cache_key(tts_text_prep.prepare(text, LANGUAGE), VOICE, RATE, PITCH)
    return tts.cache_dir / f"{key}.mp3"


def _mci(command: str) -> int:
    return ctypes.windll.winmm.mciSendStringW(command, None, 0, None)


def _play_mp3(path: Path) -> bool:
    """Plays an MP3 to the end with Windows' MCI player; False if it cannot."""
    global _counter
    if sys.platform != "win32":
        return False
    with _lock:
        _counter += 1
        alias = f"irisclick_guide_{_counter}"
    if _mci(f'open "{path}" type mpegvideo alias {alias}') != 0:
        return False
    try:
        return _mci(f"play {alias} wait") == 0
    finally:
        _mci(f"close {alias}")


player = _play_mp3  # replaced in tests


def play_cached(text: str) -> bool:
    """True when the natural voice said ``text``; False means: let pyttsx3 say it."""
    path = cached_file(text)
    if path.is_file() and player(path):
        return True
    prepare_in_background([text])
    return False


def prepare_in_background(texts: list[str]) -> None:
    """Saves natural-voice audio for these lines without blocking the caller."""
    todo = []
    with _lock:
        for text in texts:
            if text and text not in _pending and not cached_file(text).is_file():
                _pending.add(text)
                todo.append(text)
    if not todo:
        return

    def run():
        try:
            tts.warm(todo, LANGUAGE, VOICE, RATE, PITCH)
        finally:
            with _lock:
                _pending.difference_update(todo)

    runner(run)


def _thread(fn) -> None:
    threading.Thread(target=fn, name="guidance-voice", daemon=True).start()


runner = _thread  # tests run it inline


def known_lines() -> list[str]:
    """Every fixed guidance line the worker can speak (lines with changing words are
    prepared the first time they are spoken)."""
    lines = list(FIXED_LINES)
    try:
        from app.core.detection.iris_detector import DISTANCE_GUIDANCE
        from app.core.detection.lighting import LIGHTING_GUIDANCE
        lines += [*LIGHTING_GUIDANCE.values(), *DISTANCE_GUIDANCE.values()]
        # The worker runs as "python -m app.workers.tracking_worker", so it is __main__ there.
        for name in ("app.workers.tracking_worker", "__main__"):
            worker = sys.modules.get(name)
            if worker is None or not hasattr(worker, "SPEECH"):
                continue
            lines += [*getattr(worker, "SPEECH", {}).values()]
            posture = getattr(worker, "POSTURE_SPEECH", None)
            if posture:
                lines.append(posture)
    except Exception:  # noqa: BLE001 - a missing list only means fewer lines prepared
        logger.debug("Some guidance lines could not be listed", exc_info=True)
    return list(dict.fromkeys(lines))


def prepare_known_lines() -> None:
    prepare_in_background(known_lines())
