"""What "Go to ..." may open: built-in sites, built-in apps and the user's saved website tiles.

The hosted website keeps each person's Apps tiles; it hands the website tiles to
IrisClick Desktop (POST /api/desktop/voice-shortcuts), which keeps them in
storage/voice_shortcuts.json. Every address is checked again here with the same
rule as the Apps tiles (user_apps_service.clean_url: http/https, a real domain,
no spaces, no hidden user name), so a bad entry is dropped, never opened.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from app.config import STORAGE_DIR
from app.services.user_apps_service import UserAppsError, clean_url
from app.voice.commands import normalize

logger = logging.getLogger("irisclick.voice.shortcuts")

SHORTCUTS_PATH = STORAGE_DIR / "voice_shortcuts.json"
MAX_SHORTCUTS = 50
WEBSITE, APP = "website", "app"

# Always available (the same sites the Apps picker suggests).
KNOWN_SITES = {
    "facebook": "https://www.facebook.com",
    "messenger": "https://www.messenger.com",
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
}
# Built-in app keys of app/services/apps_service.py (never a path from a request).
KNOWN_APPS = {"calculator": "calculator", "calendar": "calendar", "word": "word",
              "microsoft word": "word", "excel": "excel", "powerpoint": "powerpoint",
              "browser": "browser", "keyboard": "keyboard", "on screen keyboard": "keyboard"}


@dataclass(frozen=True)
class Target:
    kind: str     # WEBSITE or APP
    label: str
    value: str    # checked URL, or an apps_service app id


def names_for(label: str, url: str) -> set[str]:
    """'YouTube' + https://www.youtube.com -> {'youtube', 'youtube.com'}."""
    names = {normalize(label)}
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    if host:
        names.add(host)
        names.add(host.split(".")[0] if host.count(".") == 1 else host)
    return {n for n in names if n}


def valid_url(url: str) -> str | None:
    try:
        return clean_url(url)
    except UserAppsError:
        return None


def load_saved(path: Path | None = None) -> list[Target]:
    path = path or SHORTCUTS_PATH  # read at call time, so tests can point it elsewhere
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    saved = []
    for row in rows[:MAX_SHORTCUTS] if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        label = " ".join(str(row.get("label", "")).split())[:40]
        url = valid_url(str(row.get("url", "")))
        if label and url:
            saved.append(Target(WEBSITE, label, url))
    return saved


def save(rows: list[dict], path: Path | None = None) -> tuple[int, int]:
    """Keeps the valid website shortcuts; returns (kept, rejected)."""
    kept, rejected = [], 0
    for row in rows[:MAX_SHORTCUTS]:
        label = " ".join(str(row.get("label", "")).split())[:40]
        url = valid_url(str(row.get("url", "")))
        if label and url and re.search(r"\w", label):
            kept.append({"label": label, "url": url})
        else:
            rejected += 1
    path = path or SHORTCUTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(kept, indent=1), encoding="utf-8")
    return len(kept), rejected


def directory(path: Path | None = None) -> dict[str, Target]:
    """Normalised spoken name -> what it opens. Saved tiles win over the built-in names."""
    found: dict[str, Target] = {}
    for name, url in KNOWN_SITES.items():
        for n in names_for(name, url):
            found[n] = Target(WEBSITE, name.title(), url)
    for name, key in KNOWN_APPS.items():
        found[name] = Target(APP, name.title(), key)
    for target in load_saved(path):
        for n in names_for(target.label, target.value):
            found[n] = target
    return found
