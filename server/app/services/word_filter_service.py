"""Word filter for Voice Communication (extension of Objective 2.5).

Masks blocked words in typed messages, Quick Phrases, the communication
board and speech-to-text results, before they are spoken or saved. Only the
masked text is ever stored. It never touches SOS alerts, and the on-screen
keyboard for other apps is out of scope.

Matching is whole-word and case-insensitive, after normalizing: accents
removed, leetspeak (@4→a 3→e 1!→i 0→o $5→s), stretched letters ("baaad" is
"bad") and split letters ("b.a.d", "b a d"). Phrases match runs of words.
An allowed word always wins. A masked word keeps its first letter: "b***".

System logs only ever name a word by its id, never the word itself.
"""

import csv
import io
import logging
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.word_filter import (
    LANGUAGES, SETTINGS_ID, TTS_BEEP, TTS_SKIP, TYPE_ALLOWED, TYPE_BLOCKED, FilteredWord, WordFilterSettings,
)
from app.services.system_log_service import log_activity

logger = logging.getLogger("irisclick.word_filter")

SEED_FILE = Path(__file__).resolve().parents[1] / "data" / "filter_seed_words.txt"
MAX_WORD = 100
MAX_IMPORT_LINES = 5000
BEEP = "beep"
LEET = str.maketrans({"@": "a", "4": "a", "3": "e", "1": "i", "!": "i", "0": "o", "$": "s", "5": "s"})
# A "word": letters, digits and the leetspeak symbols, joined by ' or -.
TOKEN = re.compile(r"[\w@$!]+(?:['’-][\w@$!]+)*")
# Split letters: three or more single characters with . - _ * or spaces between.
SPLIT = re.compile(r"(?<![\w@$])[\w@$!](?:[.\-_*\s]{1,2}[\w@$!]){2,}(?![\w@$])")


class WordFilterError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class CheckResult:
    masked_text: str
    was_filtered: bool
    matches_count: int
    speak_text: str


@dataclass
class _Lists:
    enabled: bool = True
    tts_mode: str = TTS_BEEP
    # Collapsed form -> the plain spellings on the list (see _is_stretch).
    blocked: dict[str, list[str]] = field(default_factory=dict)
    phrases: list[tuple[str, ...]] = field(default_factory=list)  # plain spellings
    allowed: set[str] = field(default_factory=set)


# --- Normalizing ----------------------------------------------------------------------------

def normalize(text: str) -> str:
    """One word or phrase in matching form: words joined by single spaces."""
    words = [_normalize_word(w) for w in TOKEN.findall(text or "")]
    return " ".join(w for w in words if w)


def _plain(word: str) -> str:
    """Lowercase, no accents, leetspeak undone; repeated letters kept."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", word) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", plain.lower().translate(LEET))


def _collapse(plain: str) -> str:
    return re.sub(r"(.)\1+", r"\1", plain)


def _normalize_word(word: str) -> str:
    return _collapse(_plain(word))


def _runs(plain: str) -> list[tuple[str, int]]:
    return [(m.group(1), len(m.group(0))) for m in re.finditer(r"(.)\1*", plain)]


def _is_stretch(written: str, listed: str) -> bool:
    """True when ``written`` is ``listed`` with some letters repeated ("baaad" for
    "bad"), never with letters missing: a short real word must not match a listed
    word that merely collapses to it (a listed "badd" never masks "bad")."""
    a, b = _runs(written), _runs(listed)
    return len(a) == len(b) and all(x == y and n >= m for (x, n), (y, m) in zip(a, b))


def _matches(written: str, lists: "_Lists") -> bool:
    return any(_is_stretch(written, listed) for listed in lists.blocked.get(_collapse(written), ()))


def _light(word: str) -> str:
    """Allowed words: only case and accents are ignored, so an allowed word that
    merely looks like a blocked one after leetspeak/stretching still wins."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", word) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", plain.lower())


def normalize_for(text: str, kind: str) -> str:
    """The stored ``normalized_word`` for a blocked or allowed entry."""
    if kind != TYPE_ALLOWED:
        return normalize(text)
    return " ".join(w for w in (_light(t) for t in TOKEN.findall(text or "")) if w)


def _usable(word: str, normalized: str) -> bool:
    """A list entry needs a real letter: "!!!" alone would otherwise block the letter i."""
    return bool(normalized) and len(word) <= MAX_WORD and re.search(r"[^\W\d_]", word) is not None


def _light_forms(token: str) -> set[str]:
    return {f for f in (_light(token), _light(token.strip("!"))) if f}


def _forms(token: str) -> set[str]:
    """A token as written, and without end punctuation ("bad!" is also "bad"), in plain form."""
    core = token.strip("!")
    return {f for f in (_plain(token), _plain(core)) if f}


# --- The cached list ------------------------------------------------------------------------

_cache: _Lists | None = None
_lock = threading.Lock()
_seeded = False


def invalidate() -> None:
    global _cache
    with _lock:
        _cache = None


def _settings_row(db: Session) -> WordFilterSettings | None:
    return db.get(WordFilterSettings, SETTINGS_ID)


def _lists(db: Session) -> _Lists:
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
    seed_from_file(db)
    lists = _Lists()
    settings = _settings_row(db)
    if settings is not None:
        lists.enabled, lists.tts_mode = settings.enabled, settings.tts_mode
    for normalized, word, kind in db.execute(
            select(FilteredWord.normalized_word, FilteredWord.word, FilteredWord.type)
            .where(FilteredWord.is_active.is_(True))):
        plain = [p for p in (_plain(t) for t in TOKEN.findall(word)) if p]
        if kind == TYPE_ALLOWED:
            lists.allowed.add(normalized)
        elif len(plain) > 1:
            lists.phrases.append(tuple(plain))
        elif plain:
            lists.blocked.setdefault(_collapse(plain[0]), []).append(plain[0])
    with _lock:
        _cache = lists
    return lists


# --- Checking -------------------------------------------------------------------------------

def _mask(original: str, per_word: bool = False) -> str:
    """Keeps the first letter or digit (of each word, for a phrase); the rest become *."""
    out, kept = [], False
    for ch in original:
        if ch.isalnum() or ch in "@$!":
            out.append(ch if not kept else "*")
            kept = True
        else:
            out.append(ch)
            kept = kept and not (per_word and ch.isspace())
    return "".join(out)


def _spans(text: str, lists: _Lists) -> list[tuple[int, int, bool]]:
    """Character ranges of text to mask (start, end, is a phrase), merged and in order."""
    found: list[tuple[int, int, bool]] = []
    tokens = [(m.start(), m.end(), m.group()) for m in TOKEN.finditer(text)]
    forms = [_forms(t) for _s, _e, t in tokens]
    allowed = [bool(_light_forms(t) & lists.allowed) for _s, _e, t in tokens]
    for (start, end, _t), f, ok in zip(tokens, forms, allowed):
        if not ok and any(_matches(w, lists) for w in f):
            found.append((start, end, False))
    for phrase in lists.phrases:
        n = len(phrase)
        for i in range(len(tokens) - n + 1):
            if all(any(_is_stretch(w, phrase[k]) for w in forms[i + k]) for k in range(n)) \
                    and not any(allowed[i:i + n]):
                found.append((tokens[i][0], tokens[i + n - 1][1], True))
    for m in SPLIT.finditer(text):
        raw = re.sub(r"[.\-_*\s]", "", m.group())
        if _matches(_plain(raw), lists) and _light(raw) not in lists.allowed:
            found.append((m.start(), m.end(), False))
    merged: list[tuple[int, int, bool]] = []
    for start, end, phrase in sorted(found):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]), merged[-1][2] and phrase)
        else:
            merged.append((start, end, phrase))
    return merged


def check(db: Session, text: str) -> CheckResult:
    lists = _lists(db)
    if not lists.enabled or not text:
        return CheckResult(text, False, 0, text)
    spans = _spans(text, lists)
    if not spans:
        return CheckResult(text, False, 0, text)
    masked, spoken, last = [], [], 0
    for start, end, phrase in spans:
        masked += [text[last:start], _mask(text[start:end], per_word=phrase)]
        spoken += [text[last:start], BEEP if lists.tts_mode == TTS_BEEP else ""]
        last = end
    masked.append(text[last:])
    spoken.append(text[last:])
    speak_text = re.sub(r"[ \t]{2,}", " ", "".join(spoken)).strip()
    return CheckResult("".join(masked), True, len(spans), speak_text)


def filter_for_storage(db: Session, text: str) -> tuple[str, bool]:
    """Hook for saving messages: (masked text, was_filtered). Never raises:
    if the filter itself fails, the message is kept as written (decision 3)."""
    try:
        result = check(db, text)
        return result.masked_text, result.was_filtered
    except Exception:  # noqa: BLE001 - the old feature must keep working
        logger.exception("Word filter failed; message saved unfiltered")
        return text, False


def mask_for_display(db: Session, text: str) -> str:
    """Hook for reports: masks older messages too. Never raises."""
    try:
        return check(db, text).masked_text
    except Exception:  # noqa: BLE001
        logger.exception("Word filter failed; report text shown as saved")
        return text


# --- Seeding from server/app/data/filter_seed_words.txt -------------------------------------

def _parse_line(line: str) -> tuple[str, str, str] | None:
    """'word[,language[,type]]' → (word, language, type); None for comments/blank."""
    line = line.strip().lstrip("﻿")
    if not line or line.startswith("#"):
        return None
    parts = next(csv.reader([line]))
    word = parts[0].strip()
    language = (parts[1].strip().lower() if len(parts) > 1 else "") or "other"
    kind = (parts[2].strip().lower() if len(parts) > 2 else "") or TYPE_BLOCKED
    if word.lower() == "word" and language in ("language", "other"):
        return None  # a header row
    return word, language if language in LANGUAGES else "other", kind if kind in (TYPE_BLOCKED, TYPE_ALLOWED) else TYPE_BLOCKED


def seed_from_file(db: Session, path: Path | None = None) -> int:
    """Adds new lines of the seed file once per server start; never re-adds a removed word."""
    global _seeded
    if _seeded and path is None:
        return 0
    path = path or SEED_FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    except OSError:
        logger.exception("Could not read the word filter seed file")
        return 0
    known = set(db.scalars(select(FilteredWord.normalized_word)))
    added = 0
    for line in lines[:MAX_IMPORT_LINES]:
        parsed = _parse_line(line)
        if parsed is None:
            continue
        word, language, kind = parsed
        normalized = normalize_for(word, kind)
        if not _usable(word, normalized) or normalized in known:
            continue
        db.add(FilteredWord(word=word, normalized_word=normalized, language=language, type=kind))
        known.add(normalized)
        added += 1
    if added:
        log_activity("word_filter_seeded", f"Word filter: {added} word(s) added from the seed file",
                     session=db)
    db.commit()
    _seeded = True
    return added


# --- Admin ----------------------------------------------------------------------------------

def get_settings(db: Session) -> WordFilterSettings:
    row = _settings_row(db)
    return row if row is not None else WordFilterSettings(setting_id=SETTINGS_ID, enabled=True, tts_mode=TTS_BEEP)


def update_settings(db: Session, admin: User, enabled: bool | None, tts_mode: str | None) -> WordFilterSettings:
    row = _settings_row(db)
    if row is None:
        row = WordFilterSettings(setting_id=SETTINGS_ID, enabled=True, tts_mode=TTS_BEEP)
        db.add(row)
    changes = []
    if enabled is not None and enabled != row.enabled:
        row.enabled = enabled
        changes.append("turned on" if enabled else "turned off")
    if tts_mode is not None and tts_mode != row.tts_mode:
        if tts_mode not in (TTS_BEEP, TTS_SKIP):
            raise WordFilterError(422, "Choose beep or skip.")
        row.tts_mode = tts_mode
        changes.append(f"speech set to {tts_mode}")
    row.updated_by = admin.user_id
    if changes:
        log_activity("word_filter_toggled", f"Word filter {', '.join(changes)} by {admin.full_name}",
                     admin.user_id, session=db)
    db.commit()
    invalidate()
    return row


def list_words(db: Session, query: str | None = None, language: str | None = None,
               kind: str | None = None, status: str = "active") -> list[FilteredWord]:
    seed_from_file(db)
    stmt = select(FilteredWord)
    if query:
        like = f"%{query.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(FilteredWord.word).like(like),
                              FilteredWord.normalized_word.like(f"%{normalize(query)}%")))
    if language in LANGUAGES:
        stmt = stmt.where(FilteredWord.language == language)
    if kind in (TYPE_BLOCKED, TYPE_ALLOWED):
        stmt = stmt.where(FilteredWord.type == kind)
    if status == "active":
        stmt = stmt.where(FilteredWord.is_active.is_(True))
    elif status == "removed":
        stmt = stmt.where(FilteredWord.is_active.is_(False))
    return list(db.scalars(stmt.order_by(func.lower(FilteredWord.word))))


def _get(db: Session, word_id: int) -> FilteredWord:
    row = db.get(FilteredWord, word_id)
    if row is None:
        raise WordFilterError(404, "That word was not found.")
    return row


def add_word(db: Session, admin: User, word: str, language: str, kind: str) -> FilteredWord:
    word = " ".join((word or "").split())
    normalized = normalize_for(word, kind)
    if not _usable(word, normalized):
        raise WordFilterError(422, f"Type a word or phrase of up to {MAX_WORD} letters.")
    if language not in LANGUAGES or kind not in (TYPE_BLOCKED, TYPE_ALLOWED):
        raise WordFilterError(422, "Choose a language and whether the word is blocked or allowed.")
    row = db.scalar(select(FilteredWord).where(FilteredWord.normalized_word == normalized))
    if row is not None and row.is_active:
        raise WordFilterError(409, f"That word is already in the list (word #{row.word_id}).")
    if row is not None:  # removed before: bring it back with the new choices
        row.is_active, row.language, row.type = True, language, kind
        verb = "restored"
    else:
        row = FilteredWord(word=word, normalized_word=normalized, language=language, type=kind,
                           created_by=admin.user_id)
        db.add(row)
        verb = "added"
    db.flush()
    log_activity(f"word_filter_{verb}", f"Word filter: word #{row.word_id} {verb} ({kind}, {language}) "
                 f"by {admin.full_name}", admin.user_id, session=db)
    db.commit()
    invalidate()
    return row


def set_active(db: Session, admin: User, word_id: int, active: bool) -> FilteredWord:
    row = _get(db, word_id)
    if row.is_active != active:
        row.is_active = active
        verb = "restored" if active else "removed"
        log_activity(f"word_filter_{verb}", f"Word filter: word #{row.word_id} {verb} by {admin.full_name}",
                     admin.user_id, session=db)
        db.commit()
        invalidate()
    return row


@dataclass(frozen=True)
class ImportResult:
    added: int
    restored: int
    skipped: int


def import_words(db: Session, admin: User, content: str) -> ImportResult:
    """A .txt or .csv: one 'word[,language[,type]]' per line; '#' comments ignored."""
    lines = (content or "").splitlines()
    if len(lines) > MAX_IMPORT_LINES:
        raise WordFilterError(413, f"Import up to {MAX_IMPORT_LINES} lines at a time.")
    existing = {r.normalized_word: r for r in db.scalars(select(FilteredWord))}
    added = restored = skipped = 0
    for line in lines:
        parsed = _parse_line(line)
        if parsed is None:
            continue
        word, language, kind = parsed
        normalized = normalize_for(word, kind)
        row = existing.get(normalized)
        if not _usable(word, normalized) or (row is not None and row.is_active):
            skipped += 1
        elif row is not None:
            row.is_active, row.language, row.type = True, language, kind
            restored += 1
        else:
            row = FilteredWord(word=" ".join(word.split()), normalized_word=normalized, language=language,
                               type=kind, created_by=admin.user_id)
            db.add(row)
            existing[normalized] = row
            added += 1
    log_activity("word_filter_imported", f"Word filter import by {admin.full_name}: {added} added, "
                 f"{restored} restored, {skipped} skipped", admin.user_id, session=db)
    db.commit()
    invalidate()
    return ImportResult(added, restored, skipped)


def export_words(db: Session, admin: User, fmt: str) -> tuple[str, str]:
    """(file text, file name) of the active list."""
    rows = list_words(db, status="active")
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["word", "language", "type"])
        writer.writerows([r.word, r.language, r.type] for r in rows)
        text, name = buffer.getvalue(), "irisclick_word_filter.csv"
    else:
        text = "# IrisClick word filter: word,language,type\n" + "".join(
            f"{r.word},{r.language},{r.type}\n" for r in rows)
        name = "irisclick_word_filter.txt"
    log_activity("word_filter_exported", f"Word filter list exported ({len(rows)} words) by {admin.full_name}",
                 admin.user_id, session=db)
    db.commit()
    return text, name


def reset_process_state() -> None:
    """Tests: forget the cache and the once-per-start seeding."""
    global _seeded
    _seeded = False
    invalidate()

