"""Where screenshots go and what they are called.

Screenshots are saved where Windows keeps its own (Win + Print Screen): the user's
Pictures\\Screenshots folder. Pictures is looked up with Windows' known-folder API, because
it is often moved (for example into OneDrive); Path.home() / "Pictures" is the fallback.

Names sort by time and say what they are:
    IrisClick_2026-11-24_20-40-00.png
    IrisClick_Test_GazeTracking_2026-11-24_20-40-00.png   (verification captures)
Two captures in the same second get _2, _3, ... instead of overwriting each other.
"""

import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

PREFIX = "IrisClick"
SUBFOLDER = "Screenshots"
SHOWN_AS = "Pictures\\Screenshots"
MAX_CONTEXT = 40
# Windows forbids \ / : * ? " < > | and control characters in file names.
_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
FOLDERID_PICTURES = "{33E28130-4E1E-4676-835A-98395C3BC3BB}"


def _known_pictures_folder() -> Path | None:
    """Windows' real Pictures folder (follows OneDrive or other redirection), or None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        raw = uuid.UUID(FOLDERID_PICTURES)
        guid = GUID(raw.time_low, raw.time_mid, raw.time_hi_version,
                    (ctypes.c_ubyte * 8).from_buffer_copy(raw.bytes[8:]))
        out = ctypes.c_wchar_p()
        shell32, ole32 = ctypes.windll.shell32, ctypes.windll.ole32
        if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return Path(out.value) if out.value else None
        finally:
            ole32.CoTaskMemFree(out)
    except Exception:  # noqa: BLE001 - any failure falls back to the home folder
        return None


def screenshots_folder(home: Path | None = None) -> Path:
    """The user's Pictures\\Screenshots folder. ``home`` (tests) skips the Windows lookup."""
    pictures = None if home is not None else _known_pictures_folder()
    return (pictures or (home or Path.home()) / "Pictures") / SUBFOLDER


def clean_part(text: str | None) -> str:
    """A safe file-name part: no illegal Windows characters, spaces become underscores."""
    cleaned = _ILLEGAL.sub("", text or "")
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._ ")
    return cleaned[:MAX_CONTEXT].rstrip("._ ")


def screenshot_name(when: datetime, context: str | None = None, test: bool = False) -> str:
    """IrisClick[_Test][_<context>]_YYYY-MM-DD_HH-MM-SS.png"""
    parts = [PREFIX] + (["Test"] if test else [])
    part = clean_part(context)
    if part:
        parts.append(part)
    return "_".join(parts) + f"_{when:%Y-%m-%d_%H-%M-%S}.png"


def reserve(folder: Path, name: str) -> Path:
    """Creates the folder and an empty file with a name nobody has taken yet; returns its path.

    Creating the file (exclusive mode) reserves the name, so two captures in the same second,
    even from two threads, get IrisClick_..._2.png, _3.png instead of overwriting.
    """
    folder.mkdir(parents=True, exist_ok=True)
    stem, suffix = name[: -len(".png")], ".png"
    for n in range(1, 1000):
        path = folder / (name if n == 1 else f"{stem}_{n}{suffix}")
        try:
            with open(path, "xb"):
                return path
        except FileExistsError:
            continue
    raise FileExistsError(f"Too many screenshots named {name}")


def save_image(image, when: datetime | None = None, folder: Path | None = None,
               context: str | None = None, test: bool = False) -> Path:
    """Saves a PIL image as a PNG in ``folder`` (default: Pictures\\Screenshots)."""
    when = when or datetime.now().astimezone()
    path = reserve(folder or screenshots_folder(), screenshot_name(when, context, test))
    try:
        image.save(path, format="PNG")
    except Exception:
        path.unlink(missing_ok=True)  # no empty file left behind
        raise
    return path
