"""App shortcuts on the Home Suite (Phase 9).

A fixed list only: the server never runs anything a request names. Each app
is shown only if this computer has it (Calendar falls back to the Google
Calendar website, as approved). Launching happens in the server process,
which runs on the user's own desktop.
"""

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("irisclick.apps")

GOOGLE_CALENDAR = "https://calendar.google.com"
BROWSER_START = "https://www.google.com"
OFFICE = {"word": "WINWORD.EXE", "excel": "EXCEL.EXE", "powerpoint": "POWERPNT.EXE"}
CALENDAR_PROTOCOLS = ("outlookcal", "ms-calendar")


@dataclass(frozen=True)
class App:
    app_id: str
    label: str
    target: str  # an executable path or a URL / protocol handed to the system
    note: str | None = None


class AppError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# --- What this computer has (replaced in tests) -------------------------------------------

def _app_path(exe: str) -> str | None:
    """Registered install path from Windows' "App Paths", if any."""
    if sys.platform != "win32":
        return None
    import winreg

    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as key:
                value, _ = winreg.QueryValueEx(key, None)
                path = str(value).strip('"')
                if Path(path).is_file():
                    return path
        except OSError:
            continue
    return None


def _has_protocol(name: str) -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, name).Close()
        return True
    except OSError:
        return False


def _calculator() -> str | None:
    path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "calc.exe"
    return str(path) if path.is_file() else None


def _open(target: str) -> None:
    os.startfile(target)  # noqa: S606 - fixed list above, never user input


finder = {"app_path": _app_path, "has_protocol": _has_protocol, "calculator": _calculator}
opener = _open


# --- Shortcuts ------------------------------------------------------------------------------

def available() -> list[App]:
    apps = [App("browser", "Browser", BROWSER_START, "Your default web browser")]
    calculator = finder["calculator"]()
    if calculator:
        apps.append(App("calculator", "Calculator", calculator))
    protocol = next((p for p in CALENDAR_PROTOCOLS if finder["has_protocol"](p)), None)
    apps.append(App("calendar", "Calendar", f"{protocol}:") if protocol else
                App("calendar", "Calendar (website)", GOOGLE_CALENDAR,
                    "Google Calendar in your browser; needs the internet"))
    for app_id, exe in OFFICE.items():
        path = finder["app_path"](exe)
        if path:
            apps.append(App(app_id, {"word": "Word", "excel": "Excel",
                                     "powerpoint": "PowerPoint"}[app_id], path))
    return apps


def launch(app_id: str) -> App:
    app = next((a for a in available() if a.app_id == app_id), None)
    if app is None:
        raise AppError(404, "That app is not available on this computer.")
    try:
        opener(app.target)
    except OSError as exc:
        logger.warning("Could not open %s: %s", app.label, exc)
        raise AppError(500, f"{app.label} could not be opened on this computer.") from exc
    return app
