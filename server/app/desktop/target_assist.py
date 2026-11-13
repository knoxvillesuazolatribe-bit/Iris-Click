"""Finds clickable controls on screen for gaze target snapping.

Windows UI Automation exposes the foreground app's buttons, links, tabs, fields
and menu items (e.g. a browser tab's "Close" X). Browsers can have large
accessibility trees, so discovery runs on its own thread and the gaze loop only
reads the latest immutable tuple; a slow app never stalls the cursor.
"""

import ctypes
import ctypes.wintypes
import logging
import threading
import tkinter as tk

from app.core.actions.target_snap import TargetRect
from app.desktop.display import foreground_window, toplevel_hwnd, window_at

logger = logging.getLogger("irisclick.target_assist")

REFRESH_SECONDS = 0.65
MAX_TARGETS = 800
# Larger "controls" are page regions, not things a user aims at.
# IrisClick's own gaze buttons, cards and text boxes are large (often 520-900 px wide), so the cap
# keeps them while still skipping whole page regions.
MAX_TARGET_WIDTH = 900
MAX_TARGET_HEIGHT = 400
MIN_TARGET_PX = 6
# Always snappable, whatever window is active: the taskbar on every screen (Start, apps, tray)
# and the desktop icons. Other windows are not scanned: they may be hidden behind the active one.
ALWAYS_WINDOW_CLASSES = ("Shell_TrayWnd", "Shell_SecondaryTrayWnd")
DESKTOP_CLASSES = ("Progman", "WorkerW")


def _class_name(hwnd) -> str:
    buffer = ctypes.create_unicode_buffer(128)
    ctypes.windll.user32.GetClassNameW(hwnd, buffer, 128)
    return buffer.value


def shell_windows() -> tuple[list[int], int | None]:
    """(the taskbar windows, the desktop-icons window or None), found by window class."""
    user32 = ctypes.windll.user32
    taskbars, icons = [], []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def each(hwnd, _):
        if user32.IsWindowVisible(hwnd) and _class_name(hwnd) in ALWAYS_WINDOW_CLASSES:
            taskbars.append(hwnd)
        if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            icons.append(hwnd)
        return True

    user32.EnumWindows(each, 0)
    return taskbars, (icons[0] if icons else None)


def window_rect(hwnd) -> tuple[int, int, int, int] | None:
    rect = ctypes.wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def _overlaps(target: TargetRect, rect) -> bool:
    left, top, right, bottom = rect
    return target.left < right and left < target.right and target.top < bottom and top < target.bottom


def visible_desktop_icons(icons, active_rect, desktop_active: bool) -> list[TargetRect]:
    """Desktop icons that are not covered by the active window (all of them when the desktop is active)."""
    if desktop_active or active_rect is None:
        return list(icons)
    return [icon for icon in icons if not _overlaps(icon, active_rect)]


def merge_targets(active, taskbar, icons, limit: int = MAX_TARGETS) -> tuple[TargetRect, ...]:
    """The active window's controls first, then the taskbar, then visible desktop icons; no duplicates."""
    merged, seen = [], set()
    for target in (*active, *taskbar, *icons):
        key = (target.left, target.top, target.right, target.bottom)
        if key not in seen:
            seen.add(key)
            merged.append(target)
    return tuple(merged[:limit])


class TargetFinder:
    def __init__(self):
        self._targets: tuple[TargetRect, ...] = ()
        self._local: tuple[TargetRect, ...] = ()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="target-finder", daemon=True)
        self.available = False

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def targets(self) -> tuple[TargetRect, ...]:
        with self._lock:
            return self._local + self._targets

    def set_local_targets(self, targets):
        """IrisClick's own Tk buttons: UI Automation does not report them."""
        with self._lock:
            self._local = tuple(targets)

    def _run(self):
        try:
            import comtypes
            import comtypes.client

            comtypes.CoInitialize()
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient as UIA

            automation = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
            condition = None
            for control_type in (
                UIA.UIA_ButtonControlTypeId, UIA.UIA_CheckBoxControlTypeId,
                UIA.UIA_ComboBoxControlTypeId, UIA.UIA_EditControlTypeId,
                UIA.UIA_HyperlinkControlTypeId, UIA.UIA_ListItemControlTypeId,
                UIA.UIA_MenuItemControlTypeId, UIA.UIA_RadioButtonControlTypeId,
                UIA.UIA_TabItemControlTypeId, UIA.UIA_TreeItemControlTypeId,
            ):
                single = automation.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, control_type)
                condition = single if condition is None else automation.CreateOrCondition(condition, single)
            self.available = True
        except Exception as exc:
            # An enhancement only: gaze keeps working without snapping.
            logger.warning("Target assistance unavailable: %s", exc)
            return

        while not self._stop.wait(REFRESH_SECONDS):
            hwnd = foreground_window()
            if not hwnd:
                continue
            def collect(window) -> list[TargetRect]:
                try:
                    elements = automation.ElementFromHandle(window).FindAll(UIA.TreeScope_Descendants, condition)
                    found = []
                    for index in range(min(elements.Length, MAX_TARGETS)):
                        element = elements.GetElement(index)
                        if not element.CurrentIsEnabled or element.CurrentIsOffscreen:
                            continue
                        rect = element.CurrentBoundingRectangle
                        target = TargetRect(int(rect.left), int(rect.top), int(rect.right),
                                            int(rect.bottom), (element.CurrentName or "").strip())
                        if (MIN_TARGET_PX <= target.width <= MAX_TARGET_WIDTH
                                and MIN_TARGET_PX <= target.height <= MAX_TARGET_HEIGHT):
                            found.append(target)
                    return found
                except Exception:
                    # Elevated/secure windows deny UI Automation; free gaze still works there.
                    return []

            active = collect(hwnd)
            taskbar, icons = [], []
            try:  # the desktop magnet: taskbar always, desktop icons when not covered
                taskbar_windows, icons_window = shell_windows()
                for window in taskbar_windows:
                    if window != hwnd:
                        taskbar += collect(window)
                if icons_window and icons_window != hwnd:
                    desktop_active = _class_name(hwnd) in DESKTOP_CLASSES
                    icons = visible_desktop_icons(collect(icons_window), window_rect(hwnd), desktop_active)
            except Exception:
                logger.debug("Desktop targets unavailable", exc_info=True)
            with self._lock:
                self._targets = merge_targets(active, taskbar, icons)


def tk_button_targets(root: tk.Misc) -> list[TargetRect]:
    """Visible, enabled tk.Buttons that are actually on top at their centre."""
    targets = []
    hwnds = {}
    stack = [root]
    while stack:
        widget = stack.pop()
        try:
            stack.extend(widget.winfo_children())
            if not isinstance(widget, tk.Button) or not widget.winfo_viewable():
                continue
            if str(widget.cget("state")) == "disabled":
                continue
            left, top = widget.winfo_rootx(), widget.winfo_rooty()
            width, height = widget.winfo_width(), widget.winfo_height()
            if width < MIN_TARGET_PX or height < MIN_TARGET_PX:
                continue
            toplevel = widget.winfo_toplevel()
            if toplevel not in hwnds:
                hwnds[toplevel] = toplevel_hwnd(toplevel)
            if window_at(left + width // 2, top + height // 2) != hwnds[toplevel]:
                continue
            targets.append(TargetRect(left, top, left + width, top + height,
                                      str(widget.cget("text")).strip()))
        except tk.TclError:
            continue
    return targets
