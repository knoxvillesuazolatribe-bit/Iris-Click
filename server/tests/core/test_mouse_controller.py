"""OS mouse actions behind the wink commands, with pyautogui replaced by a recorder (no real
cursor moves or clicks)."""

import pytest

from app.core.actions import mouse_controller
from app.core.actions.mouse_controller import USER_MOVE_PX, MouseController


class FakeOS:
    def __init__(self):
        self.cursor = (500, 400)
        self.events = []

    def size(self):
        return 1920, 1080

    def position(self):
        return self.cursor

    def moveTo(self, x, y):  # noqa: N802 - pyautogui's name
        self.cursor = (x, y)
        self.events.append(("move", x, y))

    def click(self, x, y):
        self.events.append(("click", x, y))

    def rightClick(self, x, y):  # noqa: N802 - pyautogui's name
        self.events.append(("right_click", x, y))

    def hotkey(self, *keys):
        self.events.append(("keys",) + keys)


@pytest.fixture
def os_mouse(monkeypatch):
    fake = FakeOS()
    monkeypatch.setattr(mouse_controller, "pyautogui", fake)
    return fake


def test_screen_size_and_position(os_mouse):
    mouse = MouseController()
    assert mouse.screen_size() == (1920, 1080)
    assert mouse.position() == (500, 400)


def test_a_left_wink_clicks_where_the_user_looked(os_mouse):
    MouseController().left_click(812.7, 300.2)
    assert os_mouse.events == [("click", 812, 300)]


def test_a_left_wink_without_a_point_clicks_at_the_cursor(os_mouse):
    MouseController().left_click()
    assert os_mouse.events == [("click", 500, 400)]


def test_a_right_wink_right_clicks_at_the_cursor(os_mouse):
    MouseController().right_click()
    assert os_mouse.events == [("right_click", 500, 400)]


def test_back_and_undo_keys(os_mouse):
    mouse = MouseController()
    mouse.go_back()
    mouse.undo()
    assert os_mouse.events == [("keys", "alt", "left"), ("keys", "ctrl", "z")]


def test_moves_skip_repeats_unless_forced(os_mouse):
    mouse = MouseController()
    mouse.move(10.4, 20.9)
    mouse.move(10.1, 20.2)  # same pixel
    mouse.move(10, 20, force=True)
    assert os_mouse.events == [("move", 10, 20), ("move", 10, 20)]
    assert mouse.last_sent == (10, 20)


def test_a_real_mouse_move_is_noticed(os_mouse):
    mouse = MouseController()
    assert mouse.moved_by_user() is False  # nothing sent yet
    mouse.move(100, 100)
    os_mouse.cursor = (100 + USER_MOVE_PX - 1, 100)
    assert mouse.moved_by_user() is False  # small OS nudge
    os_mouse.cursor = (100 + USER_MOVE_PX + 5, 100)
    assert mouse.moved_by_user() is True
    mouse.forget_position()
    assert mouse.moved_by_user() is False
