"""Clearer text to speech: Microsoft neural voices through edge-tts.

Order when a phrase is spoken (the site goes on to the older voices itself):
1. audio already cached on this computer (instant, works offline);
2. the neural voice online (edge-tts), with a 4-second limit for the first
   audio, then saved to the cache;
3. otherwise NeuralTtsError: the site falls back to the existing browser
   voice / Filipino internet voice, and if that fails it says so.

Text is cleaned for speaking (tts_text_prep) and passed through the word
filter by the route before it gets here. Settings are per user and live in
user_speech_settings; volume is the existing voice_volume setting.

edge-tts is an unofficial client of Microsoft's online voice service. For
production the official option is Azure Speech (API key), with the same voices.
"""

import asyncio
import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import STORAGE_DIR
from app.models.user import User
from app.models.user_speech_settings import UserSpeechSettings
from app.services import tts_text_prep
from app.services.system_log_service import log_activity

logger = logging.getLogger("irisclick.neural_tts")


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    gender: str
    accent: str


VOICES: dict[str, list[Voice]] = {
    "en": [Voice("en-PH-RosaNeural", "Rosa", "female", "Philippine English"),
           Voice("en-PH-JamesNeural", "James", "male", "Philippine English"),
           Voice("en-US-JennyNeural", "Jenny", "female", "US English"),
           Voice("en-US-GuyNeural", "Guy", "male", "US English")],
    "fil": [Voice("fil-PH-BlessicaNeural", "Blessica", "female", "Filipino"),
            Voice("fil-PH-AngeloNeural", "Angelo", "male", "Filipino")],
}
DEFAULT_VOICE = {"en": "en-PH-RosaNeural", "fil": "fil-PH-BlessicaNeural"}
DEFAULT_RATE = -10            # percent: slightly slower than normal, for clarity
RATE_RANGE = (-50, 50)
DEFAULT_PITCH = 0             # Hz
PITCH_RANGE = (-20, 20)
MAX_CHARS = 1000
FIRST_AUDIO_TIMEOUT_S = 4.0
TOTAL_TIMEOUT_S = 25.0
CACHE_LIMIT_BYTES = 200 * 1024 * 1024
MAX_WARM = 20

cache_dir: Path = STORAGE_DIR / "tts_cache"   # replaced in tests
_cache_lock = threading.Lock()
_warming: set[str] = set()


class NeuralTtsError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass
class Speech:
    audio: bytes
    boundaries: list[dict] = field(default_factory=list)  # {offset_ms, duration_ms, text}
    source: str = "neural"                                  # "neural" or "cache"
    voice: str = ""
    text: str = ""                                          # what was read aloud


@dataclass
class VoiceSettings:
    voice_en: str
    voice_fil: str
    rate: int
    pitch: int


# --- Settings (per user) --------------------------------------------------------------------

def voice_ids(language: str) -> set[str]:
    return {v.id for v in VOICES.get(language, [])}


def get_settings(db: Session, user: User) -> VoiceSettings:
    """The user's choices; anything not chosen (or no longer offered) is the default."""
    row = db.get(UserSpeechSettings, user.user_id)
    return VoiceSettings(
        voice_en=row.tts_voice_en if row and row.tts_voice_en in voice_ids("en") else DEFAULT_VOICE["en"],
        voice_fil=row.tts_voice_fil if row and row.tts_voice_fil in voice_ids("fil") else DEFAULT_VOICE["fil"],
        rate=row.tts_rate if row and row.tts_rate is not None else DEFAULT_RATE,
        pitch=row.tts_pitch if row and row.tts_pitch is not None else DEFAULT_PITCH,
    )


def _check_numbers(rate: int | None, pitch: int | None) -> None:
    if rate is not None and not RATE_RANGE[0] <= rate <= RATE_RANGE[1]:
        raise NeuralTtsError(422, f"Speed must be between {RATE_RANGE[0]}% and +{RATE_RANGE[1]}%.")
    if pitch is not None and not PITCH_RANGE[0] <= pitch <= PITCH_RANGE[1]:
        raise NeuralTtsError(422, f"Pitch must be between {PITCH_RANGE[0]} and +{PITCH_RANGE[1]}.")


def _voice_name(voice_id: str) -> str:
    return next((v.name for vs in VOICES.values() for v in vs if v.id == voice_id), voice_id)


def save_settings(db: Session, user: User, fields: dict, actor: User | None = None) -> VoiceSettings:
    voice_en, voice_fil = fields.get("voice_en"), fields.get("voice_fil")
    rate, pitch = fields.get("rate"), fields.get("pitch")
    if voice_en is not None and voice_en not in voice_ids("en"):
        raise NeuralTtsError(422, "Choose one of the English voices.")
    if voice_fil is not None and voice_fil not in voice_ids("fil"):
        raise NeuralTtsError(422, "Choose one of the Filipino voices.")
    _check_numbers(rate, pitch)
    row = db.get(UserSpeechSettings, user.user_id)
    if row is None:
        row = UserSpeechSettings(user_id=user.user_id)
        db.add(row)
    changes = []
    for attr, value, label in (("tts_voice_en", voice_en, "English voice"), ("tts_voice_fil", voice_fil, "Filipino voice"),
                               ("tts_rate", rate, "speed"), ("tts_pitch", pitch, "pitch")):
        if value is not None and getattr(row, attr) != value:
            setattr(row, attr, value)
            shown = _voice_name(value) if attr.startswith("tts_voice") else f"{value:+d}"
            changes.append(f"{label} {shown}")
    if changes:
        row.updated_by = (actor or user).user_id
        by = f" by {actor.full_name}" if actor is not None else ""
        log_activity("voice_settings_changed",
                     f"Voice settings for {user.full_name} changed ({', '.join(changes)}){by}",
                     (actor or user).user_id, session=db)
    db.commit()
    return get_settings(db, user)


def reset_settings(db: Session, user: User, actor: User | None = None) -> VoiceSettings:
    row = db.get(UserSpeechSettings, user.user_id)
    if row is not None:
        row.tts_voice_en = row.tts_voice_fil = row.tts_rate = row.tts_pitch = None
    by = f" by {actor.full_name}" if actor is not None else ""
    log_activity("voice_settings_reset", f"Voice settings for {user.full_name} reset to default{by}",
                 (actor or user).user_id, session=db)
    db.commit()
    return get_settings(db, user)


# --- The neural engine (edge-tts) -----------------------------------------------------------

async def _edge_stream(text: str, voice: str, rate: int, pitch: int) -> tuple[bytes, list[dict]]:
    import edge_tts  # imported here so the server still starts without edge-tts

    audio, marks = bytearray(), []
    got_audio = asyncio.Event()

    async def collect():
        communicate = edge_tts.Communicate(text, voice, rate=f"{rate:+d}%", pitch=f"{pitch:+d}Hz",
                                           boundary="WordBoundary", connect_timeout=4,
                                           receive_timeout=int(TOTAL_TIMEOUT_S))
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
                got_audio.set()
            elif chunk["type"] == "WordBoundary":
                marks.append({"offset_ms": chunk["offset"] // 10_000, "duration_ms": chunk["duration"] // 10_000,
                              "text": chunk["text"]})

    task = asyncio.create_task(collect())
    first = asyncio.create_task(got_audio.wait())
    done, _ = await asyncio.wait({task, first}, timeout=FIRST_AUDIO_TIMEOUT_S, return_when=asyncio.FIRST_COMPLETED)
    if not done:
        task.cancel()
        first.cancel()
        raise TimeoutError("no audio within the first-audio limit")
    first.cancel()
    await asyncio.wait_for(task, TOTAL_TIMEOUT_S)
    return bytes(audio), marks


def _edge_engine(text: str, voice: str, rate: int, pitch: int) -> tuple[bytes, list[dict]]:
    return asyncio.run(_edge_stream(text, voice, rate, pitch))


engine = _edge_engine  # replaced in tests: the test suite never calls Microsoft


# --- Cache ----------------------------------------------------------------------------------

def cache_key(text: str, voice: str, rate: int, pitch: int) -> str:
    return hashlib.sha256(f"{voice}|{rate}|{pitch}|{text}".encode("utf-8")).hexdigest()


def _read_cache(key: str) -> tuple[bytes, list[dict]] | None:
    audio_file, marks_file = cache_dir / f"{key}.mp3", cache_dir / f"{key}.json"
    try:
        audio = audio_file.read_bytes()
        marks = json.loads(marks_file.read_text(encoding="utf-8")) if marks_file.exists() else []
        os.utime(audio_file)  # recently used: removed last
        return (audio, marks) if audio else None
    except (OSError, ValueError):
        return None


def _write_cache(key: str, audio: bytes, marks: list[dict]) -> None:
    try:
        with _cache_lock:
            cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = cache_dir / f"{key}.mp3.tmp"
            tmp.write_bytes(audio)
            tmp.replace(cache_dir / f"{key}.mp3")
            (cache_dir / f"{key}.json").write_text(json.dumps(marks), encoding="utf-8")
            _prune()
    except OSError:
        logger.exception("Could not save voice audio to the cache")


def _prune() -> None:
    """Keeps the cache under CACHE_LIMIT_BYTES; the least recently used go first."""
    files = sorted(cache_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
    sizes = {f: f.stat().st_size + ((f.with_suffix(".json")).stat().st_size if f.with_suffix(".json").exists() else 0)
             for f in files}
    total = sum(sizes.values())
    for f in files:
        if total <= CACHE_LIMIT_BYTES:
            break
        total -= sizes[f]
        f.unlink(missing_ok=True)
        f.with_suffix(".json").unlink(missing_ok=True)


def cache_size_bytes() -> int:
    return sum(p.stat().st_size for p in cache_dir.glob("*")) if cache_dir.exists() else 0


# --- Speaking -------------------------------------------------------------------------------

def speak(text: str, language: str, voice: str, rate: int, pitch: int) -> Speech:
    """Neural audio for ``text`` (already through the word filter)."""
    if language not in VOICES:
        raise NeuralTtsError(422, "Choose English or Filipino.")
    if voice not in voice_ids(language):
        raise NeuralTtsError(422, "That voice is not available for this language.")
    _check_numbers(rate, pitch)
    prepared = tts_text_prep.prepare(text, language)
    if not prepared:
        raise NeuralTtsError(422, "There is nothing to say.")
    if len(prepared) > MAX_CHARS:
        raise NeuralTtsError(422, f"The voice can read up to {MAX_CHARS} characters at a time.")
    key = cache_key(prepared, voice, rate, pitch)
    cached = _read_cache(key)
    if cached is not None:
        return Speech(cached[0], cached[1], "cache", voice, prepared)
    try:
        audio, marks = engine(prepared, voice, rate, pitch)
    except ImportError as exc:
        raise NeuralTtsError(503, "The natural voice is not installed on this computer.") from exc
    except Exception as exc:  # noqa: BLE001 - timeouts, no internet, service errors
        logger.warning("Natural voice unavailable: %s", exc)
        raise NeuralTtsError(503, "The natural voice could not be reached.") from exc
    if not audio:
        raise NeuralTtsError(503, "The natural voice sent no audio.")
    _write_cache(key, audio, marks)
    return Speech(audio, marks, "neural", voice, prepared)


def warm(texts: list[str], language: str, voice: str, rate: int, pitch: int) -> None:
    """Saves audio for each text so it plays instantly (and offline) later.
    Stops at the first failure: offline means the rest would fail too."""
    for text in texts[:MAX_WARM]:
        try:
            speak(text, language, voice, rate, pitch)
        except NeuralTtsError:
            return


def warm_in_background(texts: list[str], language: str, voice: str, rate: int, pitch: int) -> bool:
    """One background job per (language, voice, rate, pitch) at a time; False if one is running."""
    job = f"{language}|{voice}|{rate}|{pitch}"
    with _cache_lock:
        if job in _warming:
            return False
        _warming.add(job)

    def run():
        try:
            warm(texts, language, voice, rate, pitch)
        finally:
            with _cache_lock:
                _warming.discard(job)

    runner(run)
    return True


def _thread(fn) -> None:
    threading.Thread(target=fn, name="tts-warm", daemon=True).start()


runner = _thread  # tests run the job inline
