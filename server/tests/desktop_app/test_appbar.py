"""The control bar reserves the top of the screen like the taskbar (found in testing: it hid the address bar)."""

from app.desktop import appbar


class FakeShell:
    def __init__(self, accept=True, move_down=0):
        self.calls, self.accept, self.move_down = [], accept, move_down

    def __call__(self, message, data):
        if message == appbar.ABM_QUERYPOS:
            data.rc.top += self.move_down  # another app bar is already at the top
        self.calls.append((message, data.uEdge, data.rc.left, data.rc.top, data.rc.right, data.rc.bottom))
        return 1 if self.accept else 0


def test_docking_registers_and_reserves_the_bars_height_across_the_screen():
    shell = FakeShell()
    strip = appbar.TopStrip(hwnd=123, screen_w=1920, send=shell)
    assert strip.dock(70) is True and strip.registered and strip.height == 70
    kinds = [c[0] for c in shell.calls]
    assert kinds == [appbar.ABM_NEW, appbar.ABM_QUERYPOS, appbar.ABM_SETPOS]
    assert shell.calls[-1] == (appbar.ABM_SETPOS, appbar.ABE_TOP, 0, 0, 1920, 70)


def test_another_bar_at_the_top_pushes_the_strip_down_but_keeps_its_height():
    shell = FakeShell(move_down=40)
    appbar.TopStrip(hwnd=1, screen_w=1366, send=shell).dock(110)
    assert shell.calls[-1][3:] == (40, 1366, 150)


def test_docking_again_only_moves_the_strip():
    shell = FakeShell()
    strip = appbar.TopStrip(hwnd=1, screen_w=1920, send=shell)
    strip.dock(70)
    strip.dock(110)  # e.g. the bar grew a second row
    assert [c[0] for c in shell.calls].count(appbar.ABM_NEW) == 1 and strip.height == 110


def test_release_gives_the_space_back_once():
    shell = FakeShell()
    strip = appbar.TopStrip(hwnd=1, screen_w=1920, send=shell)
    strip.dock(70)
    strip.release()
    strip.release()
    assert [c[0] for c in shell.calls].count(appbar.ABM_REMOVE) == 1 and not strip.registered


def test_a_refusal_or_error_never_stops_the_bar():
    assert appbar.TopStrip(hwnd=1, screen_w=1920, send=FakeShell(accept=False)).dock(70) is False

    def broken(message, data):
        raise OSError("no shell")

    strip = appbar.TopStrip(hwnd=1, screen_w=1920, send=broken)
    assert strip.dock(70) is False
    strip.release()  # nothing registered: no error
