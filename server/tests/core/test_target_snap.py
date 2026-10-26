from app.core.actions.target_snap import (
    RELEASE_SECONDS,
    SWITCH_SECONDS,
    TargetLock,
    TargetRect,
    choose_target,
)

# A maximised browser at 1920x1080: the tab close "X" in the top-right corner.
CLOSE_X = TargetRect(1874, 0, 1920, 30, "Close")
MAXIMIZE = TargetRect(1828, 0, 1874, 30, "Maximize")
ADDRESS_BAR = TargetRect(200, 40, 1500, 76, "Address and search bar")


def test_gaze_near_the_close_button_snaps_to_it():
    # Webcam gaze ~45 px below the X still selects it, not the address bar.
    assert choose_target(1905, 75, [CLOSE_X, MAXIMIZE, ADDRESS_BAR], radius=140) == CLOSE_X


def test_nothing_within_radius_keeps_free_gaze():
    assert choose_target(900, 600, [CLOSE_X, ADDRESS_BAR], radius=140) is None


def test_lock_snaps_cursor_to_target_centre():
    lock = TargetLock(radius=140)
    x, y, target = lock.snap(1900, 60, [CLOSE_X, MAXIMIZE], now=0.0)
    assert target == CLOSE_X
    assert (x, y) == CLOSE_X.center


def test_lock_holds_through_jitter_then_switches_after_dwell():
    lock = TargetLock(radius=140)
    targets = [CLOSE_X, MAXIMIZE]
    lock.snap(1897, 15, targets, now=0.0)
    # One jittery frame inside the neighbouring button does not steal the lock.
    assert lock.snap(1850, 15, targets, now=0.05)[2] == CLOSE_X
    # Resting on it for SWITCH_SECONDS does.
    assert lock.snap(1850, 15, targets, now=0.05 + SWITCH_SECONDS)[2] == MAXIMIZE


def test_lock_releases_after_looking_away():
    lock = TargetLock(radius=140)
    lock.snap(1897, 15, [CLOSE_X], now=0.0)
    lock.snap(900, 600, [CLOSE_X], now=0.1)
    x, y, target = lock.snap(900, 600, [CLOSE_X], now=0.1 + RELEASE_SECONDS)
    assert target is None
    assert (x, y) == (900, 600)
