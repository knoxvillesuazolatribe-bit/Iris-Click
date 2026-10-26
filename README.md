# IrisClick

Hands-free mouse control with an ordinary webcam. The site runs a 13-dot eye
calibration; when it succeeds, a background tracking worker starts with a
system-tray icon and moves the cursor where you look.

| Gesture | Action |
|---|---|
| Look | Moves the cursor (a yellow "V" pyramid; its tip is the pointer) |
| Small head turn / chin lift | Fine-tunes the cursor from where your eyes put it (up to 200 px) |
| Wink left eye | Left click — the only click trigger |
| Wink right eye | Go back (Alt+Left); set `RIGHT_BLINK_ACTION=undo` for Ctrl+Z |
| Blink both eyes | Nothing (ordinary blinks never trigger) |
| Move the real mouse | Gaze steps aside; it resumes 2 s after you let go |

**Target assistance:** webcam gaze is accurate to roughly 4–8 % of the screen
(~90 px), larger than small buttons. The worker reads the foreground app's
clickable controls through Windows UI Automation and snaps the pointer onto the
nearest one within 140 px, outlining it (e.g. a browser's close X). Check what
it sees with `scripts\check_targets.py`. The cursor holds still while an eye is
closing, so a wink clicks where you were looking. Dwell auto-click is off; `DWELL_CLICK_ENABLED=true` re-enables it
for users who cannot wink.

A floating control bar (top centre, drag by its label) and the tray icon both
offer pause/resume, voice on/off, recalibrate and quit. Look at a bar button and
wink left to press it; Quit asks for a second press.

Spoken guidance (offline Windows voice) tells the user when the face is not
visible, the eyes cannot be clearly detected, or they should move forward/back.
A warning is spoken only after it lasts 1.5 s and is not repeated within 25 s.

## Hybrid gaze engine

The design basis is the **nose-eye pyramid** ("0 V 0"): the nose bridge is the
anchor, the midpoint of both pupils measured from it is the pointer (the eyes
drive the cursor), and the nose-tip apex adds head direction so small head
movements do not drag the cursor.

Each camera frame produces seven feature sources: the nose-eye pyramid (iris and
pupil versions), iris-ring landmarks, fitted pupils, the eye-line midpoint (iris
and pupil versions) and GazeFollower's MGazeNet network. Calibration fits a
regression per source on the same frames. The nose-eye pyramid is used unless
another source is clearly better (25 % lower per-dot error and at least 1 % of
the screen); frames where the chosen source is missing fall back to its
landmark reference. GazeFollower's weights are CC BY-NC-SA 4.0 (non-commercial
use only).

## Run (Windows shells only, see `.claude/rules/environment.md`)

Start the server and the site in two terminals (`main.py` also opens the
calibration page):

```bat
cd server && .venv\Scripts\python main.py
cd site && pnpm dev
```

Open http://localhost:5173/calibration.

## Setup

```bat
cd server
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pip install --no-deps gazefollower==1.1.0
cd ..\site && pnpm install
```

Checks, from `server\`: `.venv\Scripts\python -m pytest` (tests),
`.venv\Scripts\python scripts\check_camera.py` (camera + engine),
`.venv\Scripts\python scripts\check_voice.py` (spoken guidance),
`.venv\Scripts\python scripts\check_targets.py 5` (target assistance; switch to the app within 5 s).

**Choosing a camera:** the calibration start screen lists every connected
camera (built-in, USB, or a phone through DroidCam/Iriun) with a snapshot and
whether a face is visible. The chosen camera is remembered on this computer
(`server/app/storage/device_settings.json`) and saved in the calibration
profile, and the tracking worker uses that same camera. Switching cameras needs
a new calibration. `CAMERA_INDEX` in `.env` is only the first-run default.

Settings live in `server/.env` (see `app/config.py`): dwell timing, blink
threshold, `SWAP_BLINK_SIDES` if winks trigger the wrong side.
Worker log: `server/app/storage/tracking_worker.log`.
