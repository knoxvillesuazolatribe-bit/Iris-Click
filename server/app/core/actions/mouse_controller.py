import math

import pyautogui

# pyautogui's corner fail-safe paused tracking whenever the user closed a
# maximised window with the real mouse (the X sits in the corner). The worker
# instead hands control to the physical mouse whenever it moves (see
# moved_by_user), which is a gentler and more general override.
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# Further than this from where gaze last put the cursor means the physical
# mouse moved it; Windows itself never nudges the cursor this far.
USER_MOVE_PX = 25.0


class MouseController:
    """Moves the OS cursor in physical pixels; the process must be DPI-aware."""

    def __init__(self):
        self._sent = None

    def screen_size(self) -> tuple[int, int]:
        width, height = pyautogui.size()
        return int(width), int(height)

    def position(self) -> tuple[int, int]:
        x, y = pyautogui.position()
        return int(x), int(y)

    def moved_by_user(self) -> bool:
        if self._sent is None:
            return False
        x, y = self.position()
        return math.hypot(x - self._sent[0], y - self._sent[1]) > USER_MOVE_PX

    def move(self, x: float, y: float, force: bool = False):
        target = (int(x), int(y))
        if force or target != self._sent:
            pyautogui.moveTo(*target)
            self._sent = target

    def forget_position(self):
        self._sent = None

    def left_click(self, x: float | None = None, y: float | None = None):
        """Click at (x, y), or where the cursor already is."""
        if x is None or y is None:
            x, y = pyautogui.position()
        pyautogui.click(int(x), int(y))
        self._sent = (int(x), int(y))

    def right_click(self):
        x, y = pyautogui.position()
        pyautogui.rightClick(x, y)

    def go_back(self):
        # Alt+Left is "Back" in browsers, File Explorer and most Windows apps.
        pyautogui.hotkey("alt", "left")

    def undo(self):
        pyautogui.hotkey("ctrl", "z")
