"""Types dictated text into whatever text box has focus, like a real keyboard.

Windows SendInput with KEYEVENTF_UNICODE sends each character as a keystroke, so
it works in any app and in rich-text boxes such as Facebook Messenger's chat box
(which ignores text set from outside but accepts real key presses). IrisClick's
control bar never takes focus, so the user's text box keeps it.
"""

import ctypes
import sys
from collections.abc import Callable

VK_RETURN, VK_SHIFT, VK_CONTROL, VK_DELETE = 0x0D, 0x10, 0x11, 0x2E
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
INPUT_KEYBOARD = 1

# A key event: ("char", "x") or ("key", vk, up?)
Event = tuple


def text_events(text: str) -> list[Event]:
    events = []
    for ch in text:
        if ch == "\n":
            events += key_combo(VK_SHIFT, VK_RETURN)  # new line without sending in chat boxes
        else:
            events.append(("char", ch))
    return events


def key_combo(*vks: int) -> list[Event]:
    return [("key", vk, False) for vk in vks] + [("key", vk, True) for vk in reversed(vks)]


class VoiceTyper:
    """Keeps a space between dictated phrases; send = Enter, clear = Ctrl+A then Delete."""

    def __init__(self, send_events: Callable[[list[Event]], None] | None = None):
        self._send = send_events or send_input
        self.typed_any = False

    def reset(self) -> None:
        self.typed_any = False

    def type_text(self, text: str) -> None:
        if not text:
            return
        self._send(text_events((" " if self.typed_any else "") + text))
        self.typed_any = True

    def send(self) -> None:
        self._send(key_combo(VK_RETURN))
        self.typed_any = False

    def new_line(self) -> None:
        self._send(key_combo(VK_SHIFT, VK_RETURN))
        self.typed_any = False

    def clear(self) -> None:
        self._send(key_combo(VK_CONTROL, ord("A")) + key_combo(VK_DELETE))
        self.typed_any = False


def send_input(events: list[Event]) -> None:
    """Windows only: one SendInput call for the whole phrase."""
    if sys.platform != "win32" or not events:
        return
    from ctypes import wintypes

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    inputs = []
    for event in events:
        if event[0] == "char":
            code = ord(event[1])
            units = [code] if code < 0x10000 else [0xD800 + ((code - 0x10000) >> 10),
                                                    0xDC00 + ((code - 0x10000) & 0x3FF)]
            for unit in units:
                for up in (False, True):
                    ki = KEYBDINPUT(0, unit, KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0), 0, 0)
                    inputs.append(INPUT(INPUT_KEYBOARD, _U(ki=ki)))
        else:
            _, vk, up = event
            ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
            inputs.append(INPUT(INPUT_KEYBOARD, _U(ki=ki)))
    array = (INPUT * len(inputs))(*inputs)
    ctypes.windll.user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
