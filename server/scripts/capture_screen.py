r"""Verification screenshot for testing and the defense dry-run: run from server\ with the venv Python.

    .venv\Scripts\python scripts\capture_screen.py GazeTracking

Saves the whole screen to the user's Pictures\Screenshots folder as
IrisClick_Test_GazeTracking_YYYY-MM-DD_HH-MM-SS.png and prints the path.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import screenshot_files  # noqa: E402


def main() -> int:
    feature = sys.argv[1] if len(sys.argv) > 1 else "Screen"
    from PIL import ImageGrab  # Pillow ships with pyautogui

    path = screenshot_files.save_image(ImageGrab.grab(), context=feature, test=True)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
