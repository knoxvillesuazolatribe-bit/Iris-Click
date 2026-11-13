"""The desktop magnet: taskbar buttons and visible desktop icons join the snap targets."""

from app.core.actions.target_snap import TargetRect
from app.desktop import target_assist as assist


def rect(left, top, right, bottom, name=""):
    return TargetRect(left, top, right, bottom, name)


ICON_LEFT = rect(10, 10, 80, 90, "Recycle Bin")
ICON_RIGHT = rect(1800, 10, 1870, 90, "Notes")
WINDOW_ON_LEFT = (0, 0, 1000, 1000)


def test_icons_covered_by_the_active_window_are_left_out():
    assert assist.visible_desktop_icons([ICON_LEFT, ICON_RIGHT], WINDOW_ON_LEFT, desktop_active=False) == [ICON_RIGHT]


def test_all_icons_count_when_the_desktop_itself_is_active():
    icons = [ICON_LEFT, ICON_RIGHT]
    assert assist.visible_desktop_icons(icons, WINDOW_ON_LEFT, desktop_active=True) == icons
    assert assist.visible_desktop_icons(icons, None, desktop_active=False) == icons


def test_active_window_first_then_taskbar_then_icons_without_duplicates():
    page_button = rect(400, 300, 900, 380, "Start calibration")
    start = rect(0, 1040, 48, 1080, "Start")
    merged = assist.merge_targets([page_button], [start, start], [ICON_RIGHT])
    assert merged == (page_button, start, ICON_RIGHT)


def test_the_overall_limit_still_holds():
    many = [rect(i, 0, i + 10, 10) for i in range(0, 2000, 11)]
    assert len(assist.merge_targets(many, many, [], limit=50)) == 50


def test_big_gaze_buttons_now_fit_the_size_limits():
    assert assist.MAX_TARGET_WIDTH >= 900 and assist.MAX_TARGET_HEIGHT >= 400
