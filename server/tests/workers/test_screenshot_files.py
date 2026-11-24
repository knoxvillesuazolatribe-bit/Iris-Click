"""Screenshots go to the user's Pictures\\Screenshots folder with clean, unique names."""

import re
import sys
import threading
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from app.config import get_settings
from app.services import screenshot_files
from app.services.screenshot_files import (SHOWN_AS, clean_part, reserve, save_image, screenshot_name,
                                           screenshots_folder)
from app.workers.screenshot_capture import ScreenshotTaker

WHEN = datetime(2026, 11, 24, 20, 40, 0)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# --- 1. Folder: resolved from the user's home, created when missing -------------------------

def test_folder_is_pictures_screenshots_under_the_given_home(tmp_path):
    assert screenshots_folder(home=tmp_path) == tmp_path / "Pictures" / "Screenshots"


def test_folder_follows_the_home_folder_without_a_windows_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(screenshot_files, "_known_pictures_folder", lambda: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert screenshots_folder() == tmp_path / "Pictures" / "Screenshots"


def test_folder_uses_windows_known_pictures_folder_when_it_is_moved(tmp_path, monkeypatch):
    onedrive = tmp_path / "OneDrive" / "Pictures"
    monkeypatch.setattr(screenshot_files, "_known_pictures_folder", lambda: onedrive)
    assert screenshots_folder() == onedrive / "Screenshots"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows known-folder API")
def test_windows_lookup_returns_the_real_pictures_folder():
    pictures = screenshot_files._known_pictures_folder()
    assert pictures is not None and pictures.is_absolute() and pictures.name


def test_missing_folder_is_created_before_saving(tmp_path):
    folder = screenshots_folder(home=tmp_path)
    assert not folder.exists()
    path = save_image(Image.new("RGB", (8, 8)), WHEN, folder)
    assert folder.is_dir() and path.parent == folder


def test_no_username_is_hard_coded():
    source = Path(screenshot_files.__file__).read_text(encoding="utf-8")
    assert "C:\\\\Users" not in source and "Knoxville" not in source


# --- 2. Names: format, sanitising, unique within the same second ------------------------------

def test_plain_name_sorts_by_time():
    assert screenshot_name(WHEN) == "IrisClick_2026-11-24_20-40-00.png"


def test_context_and_test_variants():
    assert screenshot_name(WHEN, "Notepad") == "IrisClick_Notepad_2026-11-24_20-40-00.png"
    assert screenshot_name(WHEN, "GazeTracking", test=True) == "IrisClick_Test_GazeTracking_2026-11-24_20-40-00.png"


@pytest.mark.parametrize("raw, clean", [
    ('a\\b/c:d*e?f"g<h>i|j', "abcdefghij"),
    ("  Gaze  Tracking  ", "Gaze_Tracking"),
    ("Report: Q4 / 2026?", "Report_Q4_2026"),
    ("...", ""),
    (None, ""),
    ("x" * 80, "x" * 40),
])
def test_illegal_windows_characters_are_removed(raw, clean):
    assert clean_part(raw) == clean


def test_sanitised_names_are_valid_on_windows():
    name = screenshot_name(WHEN, 'C:\\Users\\*?"<>|bad name\t')
    assert not re.search(r'[\\/:*?"<>|\x00-\x1f]', name)
    assert re.fullmatch(r"IrisClick_[A-Za-z0-9_]+_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.png", name)


def test_same_second_gets_a_counter_instead_of_overwriting(tmp_path):
    paths = [reserve(tmp_path, screenshot_name(WHEN)) for _ in range(3)]
    assert [p.name for p in paths] == ["IrisClick_2026-11-24_20-40-00.png", "IrisClick_2026-11-24_20-40-00_2.png",
                                       "IrisClick_2026-11-24_20-40-00_3.png"]


def test_rapid_parallel_saves_all_get_their_own_file(tmp_path):
    saved, errors = [], []

    def shoot():
        try:
            saved.append(save_image(Image.new("RGB", (4, 4), "teal"), WHEN, tmp_path))
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=shoot) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len({p.name for p in saved}) == 8 == len(list(tmp_path.glob("IrisClick_*.png")))


# --- 3. Capture: the handler writes a real, non-empty PNG ----------------------------------------

def _taker(folder, notes, grab=lambda: Image.new("RGB", (320, 180), "navy")):
    settings = get_settings().model_copy(update={"screenshots_dir": folder})
    return ScreenshotTaker(settings, notify=notes.append, grab=grab, background=False)


def test_capture_writes_a_valid_png_in_the_screenshots_folder(tmp_path, test_database):
    folder = screenshots_folder(home=tmp_path)
    notes = []
    assert _taker(folder, notes).take(10.0) is True
    [path] = folder.glob("*.png")
    assert re.fullmatch(r"IrisClick_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.png", path.name)
    assert path.stat().st_size > 0 and path.read_bytes()[:8] == PNG_SIGNATURE
    with Image.open(path) as image:
        assert image.format == "PNG" and image.size == (320, 180)
    assert notes == [f"Screenshot saved to {folder}"]


def test_default_folder_message_names_pictures_screenshots(tmp_path, monkeypatch, test_database):
    monkeypatch.setattr(screenshot_files, "_known_pictures_folder", lambda: tmp_path / "Pictures")
    settings = get_settings().model_copy(update={"screenshots_dir": None})
    notes = []
    taker = ScreenshotTaker(settings, notify=notes.append, grab=lambda: Image.new("RGB", (8, 8)), background=False)
    assert taker.folder == tmp_path / "Pictures" / "Screenshots"
    taker.take(10.0)
    assert notes == [f"Screenshot saved to {SHOWN_AS}"] and SHOWN_AS == "Pictures\\Screenshots"
    assert list(taker.folder.glob("IrisClick_*.png"))


def test_a_failed_grab_leaves_no_empty_file(tmp_path, test_database):
    def broken():
        raise OSError("screen not available")

    notes = []
    assert _taker(tmp_path, notes, grab=broken).take(10.0) is True
    assert list(tmp_path.glob("*.png")) == []
    assert notes == ["Screenshot failed: it could not be saved"]


def test_a_failed_png_write_removes_the_reserved_file(tmp_path):
    class Unsavable:
        def save(self, *args, **kwargs):
            raise OSError("disk full")

    with pytest.raises(OSError):
        save_image(Unsavable(), WHEN, tmp_path)
    assert list(tmp_path.glob("*.png")) == []


@pytest.mark.skipif(sys.platform != "win32", reason="needs a real Windows screen")
def test_real_screen_grab_saves_a_png(tmp_path):
    try:
        from PIL import ImageGrab
        image = ImageGrab.grab()
    except OSError:
        pytest.skip("no interactive screen (CI service session)")
    path = save_image(image, folder=tmp_path, context="GazeTracking", test=True)
    assert path.name.startswith("IrisClick_Test_GazeTracking_") and path.stat().st_size > 0
    with Image.open(path) as saved:
        assert saved.size == image.size


def test_spoken_note_reads_the_folder_naturally():
    from app.workers.worker_notes import WorkerNotes  # noqa: F401 - the module the toast lives in
    source = Path(sys.modules["app.workers.worker_notes"].__file__).read_text(encoding="utf-8")
    assert 'text.replace("\\\\", ", ")' in source
