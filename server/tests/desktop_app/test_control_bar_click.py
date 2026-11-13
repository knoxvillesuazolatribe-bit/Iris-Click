"""Clicking the control bar's label keeps the reserved top strip (found in review: windows below jumped)."""

from types import SimpleNamespace

from app.desktop.main_window import DRAG_START_PX, TOP_MARGIN_PX, ControlBar


class FakeWin:
    def __init__(self):
        self.x, self.y = 500, TOP_MARGIN_PX

    def winfo_x(self):
        return self.x

    def winfo_y(self):
        return self.y

    def winfo_reqheight(self):
        return 60

    def geometry(self, spec):
        x, y = spec.lstrip("+").split("+")
        self.x, self.y = int(x), int(y)


class FakeStrip:
    def __init__(self):
        self.calls = []

    def release(self):
        self.calls.append("release")

    def dock(self, height):
        self.calls.append(("dock", height))


def make_bar():
    bar = ControlBar.__new__(ControlBar)  # no Tk window needed for the drag logic
    bar.win, bar._strip = FakeWin(), FakeStrip()
    return bar


def at(x, y):
    return SimpleNamespace(x_root=x, y_root=y)


def test_a_plain_click_never_gives_back_the_strip():
    bar = make_bar()
    bar._start_drag(at(520, 20))
    bar._end_drag(at(520, 20))
    assert bar._strip.calls == []


def test_a_small_shake_during_a_click_is_not_a_drag():
    bar = make_bar()
    bar._start_drag(at(520, 20))
    bar._drag(at(520 + DRAG_START_PX - 2, 21))
    bar._end_drag(None)
    assert bar._strip.calls == [] and (bar.win.x, bar.win.y) == (500, TOP_MARGIN_PX)


def test_dragging_down_gives_back_the_strip_once_and_does_not_reclaim_it():
    bar = make_bar()
    bar._start_drag(at(520, 20))
    bar._drag(at(520, 200))
    bar._drag(at(520, 300))
    bar._end_drag(None)
    assert bar._strip.calls == ["release"] and bar.win.y > 2 * TOP_MARGIN_PX


def test_dragged_along_the_top_and_dropped_there_claims_the_strip_again():
    bar = make_bar()
    bar._start_drag(at(520, 20))
    bar._drag(at(800, 20))
    bar._end_drag(None)
    assert bar._strip.calls == ["release", ("dock", TOP_MARGIN_PX + 60 + TOP_MARGIN_PX)]
