"""On-screen keyboard that types into whatever app has focus (Phase 9).

A non-activating, always-on-top Tk window: pressing a key (left wink, or
dwell) never takes focus from the user's app, so pyautogui's keystrokes land
there. Opened and closed by a double both-eye blink or the control bar's
Keyboard button. Keys are 80 x 80 px with 24 px gaps (gaze UI rules).
"""

import tkinter as tk
from collections.abc import Callable

from app.desktop.display import make_tool_window

KEY_PX = 80
GAP_PX = 24
PAD_PX = 16
COLUMNS = 12
FLASH_MS = 200
BACKGROUND = "#0F1B2D"
PANEL = "#1B2B45"
TEXT = "#FFFFFF"
PRIMARY = "#4DA3FF"
ACCENT = "#FFB020"

# (label, key, column span) per row; 12 columns per row.
ROWS: list[list[tuple[str, str, int]]] = [
    [(c, c, 1) for c in "QWERTYUIOP"] + [("⌫ Backspace", "backspace", 2)],
    [(c, c, 1) for c in "ASDFGHJKL"] + [("'", "'", 1), ("↵ Enter", "enter", 2)],
    [("Caps", "caps", 1)] + [(c, c, 1) for c in "ZXCVBNM"] + [(",", ",", 1), (".", ".", 1),
                                                              ("?", "?", 1), ("!", "!", 1)],
    [("Copy", "copy", 2), ("Paste", "paste", 2), ("-", "-", 1), ("Space", "space", 4),
     ("Move ↕", "move", 2), ("✕", "close", 1)],
]


def key_action(key: str, caps: bool) -> tuple[str, tuple]:
    """What a key does: ("write", (text,)), ("press", (name,)), ("hotkey", keys),
    or a keyboard-window action ("caps" / "move" / "close")."""
    if len(key) == 1 and key.isalpha():
        return "write", (key.upper() if caps else key.lower(),)
    if key in ("backspace", "enter", "space"):
        return "press", (key,)
    if key == "copy":
        return "hotkey", ("ctrl", "c")
    if key == "paste":
        return "hotkey", ("ctrl", "v")
    if key in ("caps", "move", "close"):
        return key, ()
    return "write", (key,)


def send_keys(kind: str, args: tuple) -> None:
    import pyautogui

    if kind == "write":
        pyautogui.write(args[0])
    elif kind == "press":
        pyautogui.press(args[0])
    elif kind == "hotkey":
        pyautogui.hotkey(*args)


def keyboard_size() -> tuple[int, int, int]:
    """Width, height of the key area and the window's full height."""
    width = COLUMNS * KEY_PX + (COLUMNS - 1) * GAP_PX
    height = len(ROWS) * KEY_PX + (len(ROWS) - 1) * GAP_PX
    return width, height, height + 2 * PAD_PX + 34


class VirtualKeyboard:
    def __init__(self, root: tk.Misc, screen_w: int, screen_h: int,
                 anchor: tk.Misc | None = None,
                 send: Callable[[str, tuple], None] = send_keys,
                 on_toggle: Callable[[bool], None] | None = None):
        self.screen_w, self.screen_h = screen_w, screen_h
        self._anchor = anchor
        self._send = send
        self._on_toggle = on_toggle
        self.caps = False
        self.at_top = False
        self.visible = False
        self.buttons: dict[str, tk.Button] = {}

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=PRIMARY)
        outer = tk.Frame(self.win, bg=BACKGROUND, padx=PAD_PX, pady=PAD_PX)
        outer.pack(padx=2, pady=2)
        tk.Label(outer, text="IrisClick keyboard: types into the app you were using",
                 font=("Segoe UI", 11), bg=BACKGROUND, fg="#C9D6E8").pack(anchor="w", pady=(0, 8))
        keys_w, keys_h, _ = keyboard_size()
        area = tk.Frame(outer, bg=BACKGROUND, width=keys_w, height=keys_h)
        area.pack()
        for row_index, row in enumerate(ROWS):
            column = 0
            for label, key, span in row:
                self._key(area, label, key, column, row_index, span)
                column += span
        self.win.withdraw()
        make_tool_window(self.win)

    def _key(self, area, label, key, column, row, span):
        width = span * KEY_PX + (span - 1) * GAP_PX
        font = ("Segoe UI", 22, "bold") if len(label) == 1 else ("Segoe UI", 14, "bold")
        button = tk.Button(area, text=label, font=font, bg=PANEL, fg=TEXT,
                           activebackground=PRIMARY, activeforeground=BACKGROUND, relief="flat",
                           bd=0, highlightthickness=0, cursor="hand2",
                           command=lambda: self.press(key))
        button.place(x=column * (KEY_PX + GAP_PX), y=row * (KEY_PX + GAP_PX),
                     width=width, height=KEY_PX)
        self.buttons[key] = button

    # --- Keys --------------------------------------------------------------------------------

    def press(self, key: str) -> None:
        kind, args = key_action(key, self.caps)
        self._flash(key)
        if kind == "caps":
            self.caps = not self.caps
            self.buttons["caps"].configure(bg=ACCENT if self.caps else PANEL,
                                           fg=BACKGROUND if self.caps else TEXT)
        elif kind == "move":
            self.at_top = not self.at_top
            self._place()
        elif kind == "close":
            self.hide()
        else:
            self._send(kind, args)

    def _flash(self, key: str) -> None:
        button = self.buttons.get(key)
        if button is None or (key == "caps"):
            return
        button.configure(bg=PRIMARY, fg=BACKGROUND)
        button.after(FLASH_MS, lambda: button.configure(bg=PANEL, fg=TEXT))

    # --- Window ------------------------------------------------------------------------------

    def _place(self) -> None:
        self.win.update_idletasks()
        width, height = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        x = max(0, (self.screen_w - width) // 2)
        if self.at_top:
            top = 8
            if self._anchor is not None:
                top = self._anchor.winfo_rooty() + self._anchor.winfo_height() + 12
            y = top
        else:
            y = max(0, self.screen_h - height - 56)  # above a typical taskbar
        self.win.geometry(f"+{x}+{y}")

    def show(self) -> None:
        self._place()
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        self.visible = True
        if self._on_toggle:
            self._on_toggle(True)

    def hide(self) -> None:
        self.win.withdraw()
        self.visible = False
        if self._on_toggle:
            self._on_toggle(False)

    def toggle(self) -> bool:
        if self.visible:
            self.hide()
        else:
            self.show()
        return self.visible

    def keep_on_top(self) -> None:
        if self.visible:
            self.win.attributes("-topmost", True)
