"""Control-bar / tray keys added in Phase 6 (hook H3): Forward and Next Tab.

The control bar never takes focus, so the keys reach the app the user is in.
"""

import pyautogui

from app.desktop.system_tray import BACK, FORWARD, NEXT_TAB

KEYS = {BACK: ("alt", "left"), FORWARD: ("alt", "right"), NEXT_TAB: ("ctrl", "tab")}


def press(command: str) -> bool:
    keys = KEYS.get(command)
    if keys is None:
        return False
    pyautogui.hotkey(*keys)
    return True
