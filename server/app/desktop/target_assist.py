"""Finds clickable controls on screen for gaze target snapping.

Windows UI Automation exposes the foreground app's buttons, links, tabs, fields
and menu items (e.g. a browser tab's "Close" X). Browsers can have large
accessibility trees, so discovery runs on its own thread and the gaze loop only
reads the latest immutable tuple; a slow app never stalls the cursor.
"""

import logging
import threading
import tkinter as tk

from app.core.actions.target_snap import TargetRect
from app.desktop.display import foreground_window, toplevel_hwnd, window_at

logger = logging.getLogger("irisclick.target_assist")

REFRESH_SECONDS = 0.65
MAX_TARGETS = 800
# Larger "controls" are page regions, not things a user aims at.
MAX_TARGET_WIDTH = 520
MAX_TARGET_HEIGHT = 260
MIN_TARGET_PX = 6


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
            try:
                elements = automation.ElementFromHandle(hwnd).FindAll(UIA.TreeScope_Descendants, condition)
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
            except Exception:
                # Elevated/secure windows deny UI Automation; free gaze still works there.
                found = []
            with self._lock:
                self._targets = tuple(found)


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
