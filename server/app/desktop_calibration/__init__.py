"""Desktop calibration: the 13-point calibration in a full-screen IrisClick Desktop window.

The window is one more client of the existing ``/api/ws/calibration`` socket, so the
calibration engine, its one-at-a-time lock, the camera handling, the saved profile and
the automatic start of eye tracking are exactly the ones the website uses.

    surface.py   IRISCLICK_CALIBRATION_SURFACE = web (default) | desktop
    messages.py  version-1 messages between the website, this server and the window
    relay.py     current run state, starts the window process, passes events on
    flow.py      dot timing and steps (no screen, so it can be tested)
    client.py    the window's connections to this server
    window.py    the full-screen Tk window
    hooks.py     small helpers the launcher and the tracking worker call
"""
