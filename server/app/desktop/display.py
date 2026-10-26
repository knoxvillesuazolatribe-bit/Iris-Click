import ctypes
import tkinter as tk
from ctypes import wintypes

PROCESS_PER_MONITOR_DPI_AWARE = 2

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SWP_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED
GA_ROOT = 2

_user32 = ctypes.windll.user32
_user32.GetAncestor.restype = wintypes.HWND
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.WindowFromPoint.restype = wintypes.HWND
_user32.WindowFromPoint.argtypes = [wintypes.POINT]


def foreground_window():
    return _user32.GetForegroundWindow()


def window_at(x: float, y: float):
    """Top-level HWND of the window under a physical screen point."""
    hwnd = _user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    return _user32.GetAncestor(hwnd, GA_ROOT) if hwnd else None


def toplevel_hwnd(window: tk.Misc):
    window.update_idletasks()
    return _user32.GetAncestor(window.winfo_id(), GA_ROOT) or window.winfo_id()


def enable_dpi_awareness():
    """Make Tk, pyautogui and calibration fractions all use physical pixels.

    Must run before any window is created. Without it Windows scales the
    process and the cursor lands off-target on displays above 100% scaling.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def make_tool_window(window: tk.Misc, click_through: bool = False):
    """No taskbar button and never takes keyboard focus; optionally ignores the mouse.

    Non-activating is what lets a gaze click on our window leave keyboard
    focus in the app the user is working in.
    """
    hwnd = toplevel_hwnd(window)
    bits = WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
    if click_through:
        bits |= WS_EX_LAYERED | WS_EX_TRANSPARENT
    _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, _user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | bits)
    # Extended styles only apply after the frame is recalculated.
    _user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FLAGS)
