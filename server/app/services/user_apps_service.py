"""Customizable Apps tiles (extension of Scope p. 4: shortcuts to everyday apps).

Each user gets the six Phase 9 apps as defaults. They can hide them, add
them back, add installed apps found in the Start Menu, add websites, move
tiles and reset. Launching is by tile id only: the target always comes from
the database and is checked again here, never from the request.

Default apps still launch through ``apps_service`` exactly as before, and a
default this computer does not have stays hidden, as in Phase 9.
"""

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_app_shortcut import KIND_BUILTIN, KIND_INSTALLED, KIND_WEBSITE, UserAppShortcut
from app.services import apps_service
from app.services.apps_service import AppError
from app.services.system_log_service import log_activity

logger = logging.getLogger("irisclick.user_apps")

MAX_TILES = 12
MAX_LABEL = 40
MAX_URL = 2048
BUILTINS = {  # key -> default label, in the Phase 9 order
    "browser": "Browser", "calculator": "Calculator", "calendar": "Calendar",
    "word": "Word", "excel": "Excel", "powerpoint": "PowerPoint",
}
ALLOWED_APP_TYPES = (".lnk", ".exe")
SUGGESTIONS = [
    ("YouTube", "https://www.youtube.com", "video"),
    ("Facebook", "https://www.facebook.com", "users"),
    ("Gmail", "https://mail.google.com", "mail"),
    ("Google", "https://www.google.com", "search"),
    ("Messenger", "https://www.messenger.com", "message"),
]
SKIP_NAMES = re.compile(r"\b(uninstall|uninstaller|remove|readme|help|license|release notes)\b", re.I)


class UserAppsError(AppError):
    """Same shape as AppError (status code + friendly message)."""


@dataclass(frozen=True)
class InstalledApp:
    name: str
    path: str


@dataclass(frozen=True)
class TileView:
    tile_id: int
    label: str
    kind: str
    icon: str
    note: str | None
    available: bool
    problem: str | None


# --- What this computer has (replaced in tests) -------------------------------------------

def _start_menu_dirs() -> list[Path]:
    dirs = []
    for env in ("ProgramData", "APPDATA"):
        base = os.environ.get(env)
        if base:
            dirs.append(Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return dirs


def _scan() -> list[InstalledApp]:
    """Start Menu shortcuts of this computer, alphabetical, one per name."""
    found: dict[str, InstalledApp] = {}
    for folder in _start_menu_dirs():
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.suffix.lower() not in ALLOWED_APP_TYPES or not path.is_file():
                continue
            name = path.stem.strip()
            if not name or SKIP_NAMES.search(name):
                continue
            found.setdefault(name.casefold(), InstalledApp(name[:MAX_LABEL], str(path)))
    return sorted(found.values(), key=lambda a: a.name.casefold())


scanner = _scan
file_exists = lambda path: Path(path).is_file()  # noqa: E731 - replaced in tests


def installed_apps() -> list[InstalledApp]:
    try:
        return scanner()
    except OSError:
        logger.exception("Start Menu scan failed")
        return []


def _scanned(path: str) -> InstalledApp | None:
    wanted = os.path.normcase(os.path.normpath(path))
    return next((a for a in installed_apps()
                 if os.path.normcase(os.path.normpath(a.path)) == wanted), None)


# --- Checks ---------------------------------------------------------------------------------

def clean_url(raw: str) -> str:
    """http/https only; "youtube.com" becomes "https://youtube.com"."""
    url = (raw or "").strip()
    if not url:
        raise UserAppsError(422, "Type the website address.")
    if any(ch.isspace() or ord(ch) < 32 for ch in url):
        raise UserAppsError(422, "A website address cannot contain spaces.")
    if "://" not in url and ":" not in url.split("/")[0]:
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or "." not in parts.hostname:
        raise UserAppsError(422, "Only website addresses starting with http:// or https:// can be added.")
    if len(url) > MAX_URL:
        raise UserAppsError(422, "That website address is too long.")
    return url


def _clean_label(raw: str | None) -> str:
    label = " ".join((raw or "").split())
    if not label:
        raise UserAppsError(422, "Give the app a name.")
    return label[:MAX_LABEL]


def _website_icon(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    for _name, suggestion, icon in SUGGESTIONS:
        if (urlsplit(suggestion).hostname or "").removeprefix("www.") == host:
            return icon
    return "globe"


# --- Reading --------------------------------------------------------------------------------

def _rows(db: Session, user: User) -> list[UserAppShortcut]:
    return list(db.scalars(select(UserAppShortcut).where(UserAppShortcut.user_id == user.user_id)
                           .order_by(UserAppShortcut.position, UserAppShortcut.shortcut_id)))


def ensure_defaults(db: Session, user: User) -> None:
    """On first use, give the user the six Phase 9 apps."""
    if db.scalar(select(UserAppShortcut.shortcut_id).where(UserAppShortcut.user_id == user.user_id).limit(1)):
        return
    for position, (key, label) in enumerate(BUILTINS.items()):
        db.add(UserAppShortcut(user_id=user.user_id, label=label, type=KIND_BUILTIN, builtin_key=key,
                               icon=key, position=position, is_visible=True))
    log_activity("app_tiles_created", f"Default apps set up for {user.full_name}", user.user_id, session=db)
    try:
        db.commit()
    except IntegrityError:  # two first loads at once: the other one won
        db.rollback()


def _builtins_here() -> dict[str, apps_service.App]:
    return {a.app_id: a for a in apps_service.available()}


def _view(row: UserAppShortcut, here: dict[str, apps_service.App]) -> TileView | None:
    """How a visible row shows on Home; None for a default this computer lacks."""
    if row.type == KIND_BUILTIN:
        app = here.get(row.builtin_key or "")
        if app is None:
            return None
        return TileView(row.shortcut_id, app.label, row.type, row.icon, app.note, True, None)
    if row.type == KIND_INSTALLED:
        ok = bool(row.target) and file_exists(row.target)
        return TileView(row.shortcut_id, row.label, row.type, row.icon, None, ok,
                        None if ok else f"{row.label} isn't installed on this computer.")
    return TileView(row.shortcut_id, row.label, row.type, row.icon, "Website; needs the internet", True, None)


def overview(db: Session, user: User) -> dict:
    ensure_defaults(db, user)
    here = _builtins_here()
    rows = _rows(db, user)
    tiles = [v for r in rows if r.is_visible and (v := _view(r, here))]
    hidden = [{"tile_id": r.shortcut_id, "label": here[r.builtin_key].label, "icon": r.icon}
              for r in rows if r.type == KIND_BUILTIN and not r.is_visible and r.builtin_key in here]
    return {"tiles": tiles, "hidden_defaults": hidden, "max_tiles": MAX_TILES,
            "suggestions": [{"label": n, "url": u, "icon": i} for n, u, i in SUGGESTIONS]}


def _shown_count(db: Session, user: User) -> int:
    here = _builtins_here()
    return sum(1 for r in _rows(db, user) if r.is_visible and _view(r, here))


def _own(db: Session, user: User, tile_id: int) -> UserAppShortcut:
    row = db.get(UserAppShortcut, tile_id)
    if row is None or row.user_id != user.user_id:
        raise UserAppsError(404, "That app was not found. It may already be removed.")
    return row


# --- Changes --------------------------------------------------------------------------------

def _who(user: User, actor: User | None) -> str:
    return f" by {actor.full_name}" if actor is not None else ""


def _check_room(db: Session, user: User) -> None:
    if _shown_count(db, user) >= MAX_TILES:
        raise UserAppsError(409, f"You can have up to {MAX_TILES} apps. Remove one first.")


def _end_position(db: Session, user: User) -> int:
    return max((r.position for r in _rows(db, user)), default=-1) + 1


def add(db: Session, user: User, fields: dict, actor: User | None = None) -> UserAppShortcut:
    """fields: kind + builtin_key | path | label & url."""
    ensure_defaults(db, user)
    kind = fields.get("kind")
    if kind == KIND_BUILTIN:
        row = next((r for r in _rows(db, user) if r.builtin_key == fields.get("builtin_key")), None)
        if row is None or fields.get("builtin_key") not in _builtins_here():
            raise UserAppsError(404, "That app is not available on this computer.")
        if row.is_visible:
            raise UserAppsError(409, f"{row.label} is already in your apps.")
        return set_visible(db, user, row.shortcut_id, True, actor)
    _check_room(db, user)
    if kind == KIND_INSTALLED:
        path = fields.get("path") or ""
        if Path(path).suffix.lower() not in ALLOWED_APP_TYPES:
            raise UserAppsError(422, "Only apps from the Start Menu can be added.")
        found = _scanned(path)
        if found is None:
            raise UserAppsError(422, "That app was not found in this computer's Start Menu.")
        row = UserAppShortcut(user_id=user.user_id, label=found.name, type=KIND_INSTALLED,
                              target=found.path, icon="app")
    elif kind == KIND_WEBSITE:
        url = clean_url(fields.get("url") or "")
        row = UserAppShortcut(user_id=user.user_id, label=_clean_label(fields.get("label")),
                              type=KIND_WEBSITE, target=url, icon=_website_icon(url))
    else:
        raise UserAppsError(422, "Choose a default app, an installed app or a website.")
    if any(r.target and r.target.casefold() == row.target.casefold() for r in _rows(db, user)):
        raise UserAppsError(409, f"{row.label} is already in your apps.")
    row.position = _end_position(db, user)
    row.is_visible = True
    db.add(row)
    db.flush()
    log_activity("app_tile_added", f"{row.label} added to the apps of {user.full_name}{_who(user, actor)}",
                 user.user_id, session=db)
    db.commit()
    db.refresh(row)
    return row


def set_visible(db: Session, user: User, tile_id: int, visible: bool,
                actor: User | None = None) -> UserAppShortcut:
    row = _own(db, user, tile_id)
    if row.is_visible == visible:
        return row
    if visible:
        _check_room(db, user)
        row.position = _end_position(db, user)
    row.is_visible = visible
    verb = "added back to" if visible else "removed from"
    log_activity("app_tile_restored" if visible else "app_tile_removed",
                 f"{row.label} {verb} the apps of {user.full_name}{_who(user, actor)}",
                 user.user_id, session=db)
    db.commit()
    db.refresh(row)
    return row


def move(db: Session, user: User, tile_id: int, position: int, actor: User | None = None) -> None:
    """Puts the tile at ``position`` among the tiles shown on Home (0 = first)."""
    row = _own(db, user, tile_id)
    here = _builtins_here()
    shown = [r for r in _rows(db, user) if r.is_visible and _view(r, here)]
    if row not in shown:
        raise UserAppsError(409, "Only apps shown on Home can be moved.")
    shown.remove(row)
    shown.insert(max(0, min(position, len(shown))), row)
    rest = [r for r in _rows(db, user) if r not in shown]
    for index, r in enumerate([*shown, *rest]):
        r.position = index
    log_activity("app_tile_reordered", f"{row.label} moved in the apps of {user.full_name}{_who(user, actor)}",
                 user.user_id, session=db)
    db.commit()


def remove(db: Session, user: User, tile_id: int, actor: User | None = None) -> None:
    """Defaults are hidden so they can come back; added apps are deleted."""
    row = _own(db, user, tile_id)
    if row.type == KIND_BUILTIN:
        set_visible(db, user, tile_id, False, actor)
        return
    label = row.label
    db.delete(row)
    log_activity("app_tile_removed", f"{label} removed from the apps of {user.full_name}{_who(user, actor)}",
                 user.user_id, session=db)
    db.commit()


def reset(db: Session, user: User, actor: User | None = None) -> None:
    """Back to the original six; added apps and websites are removed."""
    ensure_defaults(db, user)
    order = list(BUILTINS)
    for row in _rows(db, user):
        if row.type == KIND_BUILTIN:
            row.is_visible = True
            row.position = order.index(row.builtin_key) if row.builtin_key in order else len(order)
        else:
            db.delete(row)
    log_activity("app_tiles_reset", f"Apps of {user.full_name} reset to the defaults{_who(user, actor)}",
                 user.user_id, session=db)
    db.commit()


# --- Launch ---------------------------------------------------------------------------------

def launch(db: Session, user: User, tile_id: int) -> str:
    """Opens the tile's app; returns its label. Raises UserAppsError/AppError."""
    row = _own(db, user, tile_id)
    if not row.is_visible:
        raise UserAppsError(404, "That app is not in your apps.")
    if row.type == KIND_BUILTIN:
        label = apps_service.launch(row.builtin_key or "").label  # unchanged Phase 9 launch
    else:
        target = _checked_target(row)
        try:
            apps_service.opener(target)
        except OSError as exc:
            logger.warning("Could not open %s: %s", row.label, exc)
            raise UserAppsError(500, f"{row.label} could not be opened on this computer.") from exc
        label = row.label
    log_activity("app_launched", f"{user.full_name} opened {label}", user.user_id, session=db)
    db.commit()
    return label


def _checked_target(row: UserAppShortcut) -> str:
    """Re-checks a saved target right before it is opened."""
    if row.type == KIND_WEBSITE:
        return clean_url(row.target or "")
    path = row.target or ""
    if Path(path).suffix.lower() not in ALLOWED_APP_TYPES:
        raise UserAppsError(422, f"{row.label} cannot be opened from IrisClick.")
    if not file_exists(path) or _scanned(path) is None:
        raise UserAppsError(404, f"{row.label} isn't installed on this computer.")
    return path
