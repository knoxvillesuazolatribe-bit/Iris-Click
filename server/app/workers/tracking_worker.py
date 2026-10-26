"""Background eye-tracking app: floating control bar, tray icon, gaze cursor,
eye commands and spoken guidance.

Run with ``pythonw -m app.workers.tracking_worker [--profile-id ID]`` from
``server/`` (the tracking service does this after a successful calibration).

  look        moves the cursor (the "V" pyramid overlay shows the pointer)
  left wink   left click, the only click trigger
  right wink  go back (Alt+Left) or undo (Ctrl+Z), see RIGHT_BLINK_ACTION
  both eyes   nothing: ordinary blinks never trigger
  dwell       off unless DWELL_CLICK_ENABLED=true (no UI toggle on purpose)

Threads: the GazeTracker camera thread, pystray's loop and the voice thread
only hand data to the Tk main thread, which owns every window and OS-input call.
"""

import argparse
import json
import logging
import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from logging.handlers import RotatingFileHandler

from app.config import Settings, get_settings
from app.core.actions.dwell_click import DwellClicker
from app.core.actions.mouse_controller import MouseController
from app.core.actions.target_snap import TargetLock
from app.core.calibration.profile import load_profile
from app.core.detection.blink_detector import LEFT, RIGHT, BlinkDetector
from app.core.detection.iris_detector import distance_advice
from app.core.detection.lighting import LIGHTING_GUIDANCE
from app.core.gaze.estimator import GazeTracker
from app.core.gaze.blink_anchor import BlinkAnchor
from app.core.gaze.head_nudge import HeadNudge
from app.core.gaze.pipeline import TRANSIENT_REASONS, GazePipeline
from app.core.gaze.smoothing import CursorGlide, GazeStabilizer
from app.desktop.display import enable_dpi_awareness
from app.desktop.gaze_overlay import GazeOverlay
from app.desktop.main_window import ControlBar
from app.desktop.system_tray import (
    PAUSE,
    QUIT,
    RECALIBRATE,
    TOGGLE_VOICE,
    SystemTray,
)
from app.desktop.target_assist import TargetFinder, tk_button_targets
from app.desktop.voice import Speaker, VoiceGuide
from app.services.camera_service import get_camera_service
from app.services.tracking_service import pid_alive, stop_request_path

TICK_MS = 20
STOP_CHECK_EVERY_TICKS = 25
TOPMOST_EVERY_TICKS = 100
LOCAL_TARGETS_EVERY_TICKS = 50
CAMERA_RETRY_S = 3.0
CAMERA_START_ATTEMPTS = 4
CURSOR_DEADZONE_PX = 4.0
# Eyes re-settle for a moment after reopening; hold the cursor meanwhile.
POST_BLINK_HOLD_S = 0.3
# Fixation-lock radius at smoothing 0 and the extra range up to smoothing 1.
# Measured webcam jitter is ~30 px/frame with 100-160 px steps, so the default
# smoothing (0.25) locks within 80 px.
FIXATION_RADIUS_MIN_PX = 40.0
FIXATION_RADIUS_RANGE_PX = 160.0

REASON_TEXT = {
    "no_face": "Face not visible. Face the screen or improve the lighting.",
    "stale": "Camera image paused. Check the webcam connection.",
    "invalid_features": "Eyes are not clear. Move closer or adjust lighting.",
    "invalid_eyes": "Eyes are not clear. Move closer or adjust lighting.",
    "missing_features": "Eyes are not clear. Move closer or recalibrate.",
    "invalid_prediction": "Calibration result is invalid. Choose Recalibrate.",
    "invalid_timestamp": "Camera timing is unclear. Reconnect the webcam.",
}

EYES_UNCLEAR_SPEECH = ("Your eyes cannot be clearly detected. Please move forward a little "
                       "and face the screen.")
SPEECH = {
    "no_face": "I cannot see your face. Please face the camera.",
    "invalid_features": EYES_UNCLEAR_SPEECH,
    "invalid_eyes": EYES_UNCLEAR_SPEECH,
    "missing_features": EYES_UNCLEAR_SPEECH,
    "closer": "Please move forward a little. Your eyes are too small for the camera.",
    "back": "Please move back a little. You are too close to the camera.",
    "camera": "The camera stopped. I will try to reconnect.",
}
DISTANCE_TEXT = {
    "closer": "Move forward a little: eyes are too small for the camera.",
    "back": "Move back a little: too close to the camera.",
}

logger = logging.getLogger("irisclick.worker")


def configure_logging(settings: Settings):
    settings.worker_log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(settings.worker_log_path, maxBytes=1_000_000,
                                  backupCount=3, encoding="utf-8")
    # pythonw has no console: sys.stderr is None, so log to file only.
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class PidFile:
    def __init__(self, settings: Settings):
        self.path = settings.worker_pid_path
        self.stop_path = stop_request_path(self.path)

    def claim(self, profile_id: str) -> bool:
        """Record this process; False if another live worker already owns it."""
        try:
            other = json.loads(self.path.read_text("utf-8")).get("pid")
        except (OSError, ValueError, AttributeError):
            other = None
        if isinstance(other, int) and other != os.getpid() and pid_alive(other):
            return False
        self.stop_path.unlink(missing_ok=True)
        self.path.write_text(json.dumps({
            "pid": os.getpid(), "profile_id": profile_id,
            "started_at": datetime.now().astimezone().isoformat(),
        }), encoding="utf-8")
        return True

    def stop_requested(self) -> bool:
        return self.stop_path.exists()

    def release(self):
        try:
            if json.loads(self.path.read_text("utf-8")).get("pid") == os.getpid():
                self.path.unlink(missing_ok=True)
        except (OSError, ValueError, AttributeError):
            pass
        self.stop_path.unlink(missing_ok=True)


class TrackingWorker:
    def __init__(self, settings: Settings, tracker: GazeTracker, model, pid_file: PidFile):
        self.settings = settings
        self.tracker = tracker
        self.model = model
        self.pid_file = pid_file
        self.mouse = MouseController()
        self.screen_w, self.screen_h = self.mouse.screen_size()

        self.commands: queue.Queue[str] = queue.Queue()
        self.root = tk.Tk()
        self.root.title("IrisClick")
        self.overlay = GazeOverlay(self.root, self.screen_w, self.screen_h)
        self.bar = ControlBar(self.root, self.commands, self.screen_w)
        self.tray = SystemTray(self.commands)
        self.speaker = Speaker()
        self.voice = VoiceGuide(self.speaker)
        self.voice.enabled = settings.voice_guidance_enabled

        self.pipeline = GazePipeline()
        self.blink = BlinkDetector(threshold=settings.blink_threshold)
        self.stabilizer = GazeStabilizer(radius=FIXATION_RADIUS_MIN_PX
                                         + settings.cursor_smoothing * FIXATION_RADIUS_RANGE_PX)
        self.glide = CursorGlide()
        self.nudge = HeadNudge(gain_px=settings.head_fine_tune_gain_px,
                               max_offset_px=settings.head_fine_tune_max_px)
        self.dwell = DwellClicker(radius_px=settings.dwell_radius_px, dwell_ms=settings.dwell_ms,
                                  cooldown_ms=settings.dwell_cooldown_ms)
        self.dwell_enabled = settings.dwell_click_enabled
        self.targets = TargetFinder()
        self.target_lock = TargetLock(radius=settings.target_snap_radius_px)
        self._target = None
        self._handoff_until = 0.0
        self._handoff_pos = None
        self.blink_anchor = BlinkAnchor()
        self._lid_down = False
        self._wink_point = None
        self._hold_until = 0.0
        self.paused = False
        self._pause_reason = ""
        self._was_paused = False
        self._last_cursor = None
        self._showing_cursor = False
        self._tick_count = 0
        self._camera_restart: threading.Thread | None = None
        self._next_camera_retry = 0.0
        self._quitting = False

    def run(self):
        self.tray.start()
        self.speaker.start()
        if self.settings.target_snap_enabled:
            self.targets.start()
        self.voice.announce("Eye tracking is on.", time.monotonic())
        self.root.after(TICK_MS, self._tick)
        try:
            self.root.mainloop()
        finally:
            self.tray.stop()
            self.speaker.stop()
            self.targets.stop()

    def quit(self):
        if self._quitting:
            return
        self._quitting = True
        logger.info("Tracking worker quitting")
        self.root.after(0, self.root.destroy)

    def _set_status(self, text: str, kind: str):
        state = (kind, self.paused, self.voice.enabled)
        self.bar.set_state(text, *state)
        self.tray.set_state(f"IrisClick: {text}", *state)

    def _pause(self, reason: str):
        self.paused = True
        self._pause_reason = reason
        self._reset_motion()
        logger.info("Tracking paused: %s", reason)
        self.voice.announce(f"Tracking paused. {reason} Choose Resume to continue.",
                            time.monotonic())

    def _reset_motion(self):
        self.pipeline.reset()
        self.stabilizer.reset()
        self.nudge.reset()
        self.glide.reset()
        self.dwell.reset()
        self.target_lock.reset()
        self.blink_anchor.reset()
        self._wink_point = None
        self._target = None
        self._last_cursor = None
        self._showing_cursor = False
        self.mouse.forget_position()

    def _mouse_in_use(self, now: float) -> bool:
        """True while the physical mouse is being used; gaze steps aside."""
        if now < self._handoff_until:
            position = self.mouse.position()
            if position != self._handoff_pos:
                self._handoff_pos = position
                self._handoff_until = now + self.settings.mouse_handoff_s
            return True
        if self._handoff_pos is not None:
            self._handoff_pos = None
            self._reset_motion()
            logger.info("Physical mouse released; gaze resumed")
            return False
        if self.mouse.moved_by_user():
            self._handoff_pos = self.mouse.position()
            self._handoff_until = now + self.settings.mouse_handoff_s
            self._reset_motion()
            logger.info("Physical mouse in use; gaze handed off")
            return True
        return False

    def _handle_commands(self):
        while not self.commands.empty():
            command = self.commands.get_nowait()
            now = time.monotonic()
            if command == PAUSE:
                if self.paused:
                    self.paused, self._pause_reason = False, ""
                    self.voice.announce("Tracking resumed.", now)
                else:
                    self._pause("")
            elif command == TOGGLE_VOICE:
                self.voice.enabled = not self.voice.enabled
                if self.voice.enabled:
                    self.voice.announce("Voice guidance on.", now)
            elif command == RECALIBRATE:
                webbrowser.open(f"{self.settings.site_url.rstrip('/')}/calibration")
                self.quit()
            elif command == QUIT:
                self.quit()

    def _hide(self, text: str, kind: str):
        self.overlay.hide_cursor()
        self._showing_cursor = False
        self._set_status(text, kind)

    def _tick(self):
        if self._quitting:
            return
        self._tick_count += 1
        try:
            self._step()
        except Exception as exc:
            logger.exception("Tracking step failed: %s", exc)
            self._pause("Something went wrong.")
        if not self._quitting:
            self.root.after(TICK_MS, self._tick)

    def _step(self):
        self._handle_commands()
        if self._quitting:
            return
        if self._tick_count % STOP_CHECK_EVERY_TICKS == 0 and self.pid_file.stop_requested():
            self.quit()
            return
        if self._tick_count % TOPMOST_EVERY_TICKS == 0:
            self.overlay.keep_on_top()
            self.bar.keep_on_top()
        if self._tick_count % LOCAL_TARGETS_EVERY_TICKS == 1:
            self.targets.set_local_targets(tk_button_targets(self.bar.win))
        now_s = time.monotonic()

        if not self.paused and self._mouse_in_use(now_s):
            self.blink.reset()
            self._hide("Mouse in use. Gaze resumes when you let go.", "paused")
            return

        if self.tracker.last_error or not self.tracker.running:
            self._recover_camera()
            self._reset_motion()
            self.voice.observe("camera", SPEECH["camera"], now_s)
            self._hide("Camera stopped, reconnecting…", "problem")
            return

        reading = self.tracker.read()
        estimate = self.pipeline.process(reading, self.model, self.settings.cursor_smoothing,
                                         output_size=(self.screen_w, self.screen_h))
        reason = self.pipeline.reason
        lighting = LIGHTING_GUIDANCE.get(reading.lighting_status)
        distance = distance_advice(reading.eye_line) if reading.face_found else None

        if self.paused:
            self.voice.observe(None, None, now_s)
        elif reason not in TRANSIENT_REASONS:
            self.voice.observe(*self._problem_speech(reason, lighting, distance), now_s)
        elif distance:
            # Tracking still works out of range, but each eye covers too few
            # (or too many) pixels for accurate gaze.
            self.voice.observe(distance, SPEECH[distance], now_s)
        else:
            self.voice.observe(None, None, now_s)

        if reason not in TRANSIENT_REASONS:
            self.blink.reset()
            self._reset_motion()
            self._hide(lighting or REASON_TEXT.get(reason, "Waiting for a clear camera image."),
                       "problem")
            return

        eye_ear = min(reading.left_ear, reading.right_ear)
        eye_closing = eye_ear < self.settings.blink_threshold
        if eye_closing and not self._lid_down and not self.paused:
            self._lid_down = True
            # The lid dragged the cursor before the eye counted as closed; go
            # back to where the user was looking and click there.
            self._wink_point = self.blink_anchor.anchor()
            if self._wink_point is not None and self._showing_cursor:
                self.glide.reset()
                self.mouse.move(*self._wink_point, force=True)
                self.overlay.show_cursor(*self._wink_point, 0.0, self._target_rect())
        if reason != "duplicate":
            self._handle_blink(reading)

        if eye_closing and not self.paused:
            self.dwell.reset()
            return
        if self._lid_down:
            self._lid_down = False
            self._hold_until = now_s + POST_BLINK_HOLD_S
        if now_s < self._hold_until and not self.paused:
            # Eyes re-settle after reopening; that motion is not a gaze shift.
            # A fresh fixation starts when the hold ends.
            self.stabilizer.reset()
            self.nudge.reset()
            self.dwell.reset()
            return
        self._wink_point = None

        if self.paused:
            self._was_paused = True
            self.dwell.reset()
            self._hide(f"Paused. {self._pause_reason}".strip(), "paused")
            return
        if self._was_paused:
            self._was_paused = False
            self._reset_motion()
            estimate = self.pipeline.process(reading, self.model, self.settings.cursor_smoothing,
                                             output_size=(self.screen_w, self.screen_h))
            reason = self.pipeline.reason

        now = time.perf_counter()
        if reason == "duplicate":
            self._glide(now)
            return
        if estimate is None:
            self.dwell.reset()
            self._hide("Waiting for eyes to reopen", "tracking")
            return

        x = min(max(estimate.x, 0.0), self.screen_w - 1.0)
        y = min(max(estimate.y, 0.0), self.screen_h - 1.0)
        x, y = self.stabilizer.update(x, y, reading.captured_at,
                                      eye_difference=(reading.features[2], reading.features[3]))
        if self.settings.head_fine_tune_enabled:
            apex = (reading.eye_line or {}).get("nose_apex")
            dx, dy = self.nudge.update(apex, self.stabilizer.anchor_id, reading.captured_at)
            x = min(max(x + dx, 0.0), self.screen_w - 1.0)
            y = min(max(y + dy, 0.0), self.screen_h - 1.0)
        self._target = None
        if self.settings.target_snap_enabled:
            x, y, self._target = self.target_lock.snap(x, y, self.targets.targets(), now_s)
        # Tiny landmark fluctuations must not vibrate the OS cursor or keep
        # re-anchoring the dwell timer.
        if self._last_cursor is not None and math.dist((x, y), self._last_cursor) < CURSOR_DEADZONE_PX:
            x, y = self._last_cursor
        else:
            self._last_cursor = (x, y)

        self.glide.set_target(x, y, now)
        gx, gy = self.glide.position(now)
        self.mouse.move(gx, gy, force=True)
        if self.dwell_enabled and self.dwell.update(x, y):
            self.mouse.left_click(x, y)
            self.glide.reset()
            self.glide.set_target(x, y, now)
            gx, gy = x, y
        self._draw(gx, gy, DISTANCE_TEXT.get(distance))
        self.blink_anchor.record(now_s, gx, gy, eye_ear)

    @staticmethod
    def _problem_speech(reason, lighting, distance):
        if lighting:
            return reason, lighting
        if distance and reason != "no_face":
            # Unclear eyes plus a known distance problem: say what to fix.
            return distance, SPEECH[distance]
        return reason, SPEECH.get(reason)

    def _glide(self, now: float):
        if not self._showing_cursor:
            return
        position = self.glide.position(now)
        if position is None:
            return
        self.mouse.move(*position)
        self.overlay.show_cursor(*position, self._dwell_progress(), self._target_rect())

    def _dwell_progress(self) -> float:
        return self.dwell.progress() if self.dwell_enabled else 0.0

    def _target_rect(self):
        t = self._target
        return (t.left, t.top, t.right, t.bottom) if t is not None else None

    def _draw(self, x: float, y: float, warning: str | None):
        self.overlay.show_cursor(x, y, self._dwell_progress(), self._target_rect())
        self._showing_cursor = True
        if warning:
            self._set_status(warning, "problem")
        elif self._target is not None:
            self._set_status(f"Target: {self._target.name[:30] or 'button'}. Wink left to click.",
                             "tracking")
        else:
            source = "landmark fallback" if self.pipeline.using_reference_model else "Tracking"
            self._set_status(source, "tracking")

    def _handle_blink(self, reading):
        side = self.blink.update(reading.left_ear, reading.right_ear)
        if side is None or self.paused:
            return
        if self.settings.swap_blink_sides:
            side = {LEFT: RIGHT, RIGHT: LEFT}.get(side, side)
        if side == LEFT:
            if self._wink_point is not None:
                self.mouse.left_click(*self._wink_point)
            else:
                self.mouse.left_click()
            logger.info("Left wink: left click")
        elif side == RIGHT:
            if self.settings.right_blink_action == "undo":
                self.mouse.undo()
            else:
                self.mouse.go_back()
            logger.info("Right wink: %s", self.settings.right_blink_action)
        self.dwell.reset()

    def _recover_camera(self):
        if self._camera_restart is not None and self._camera_restart.is_alive():
            return
        if time.monotonic() < self._next_camera_retry:
            return
        self._next_camera_retry = time.monotonic() + CAMERA_RETRY_S

        def restart():
            try:
                self.tracker.stop()
                self.tracker.start()
                logger.info("Camera reconnected")
            except RuntimeError as exc:
                logger.warning("Camera reconnect failed: %s", exc)

        self._camera_restart = threading.Thread(target=restart, name="camera-restart", daemon=True)
        self._camera_restart.start()


def start_tracker(settings: Settings, camera_index: int) -> GazeTracker:
    tracker = GazeTracker(settings.face_model_path, camera_index=camera_index,
                          refine_pupils=settings.refine_pupils,
                          deep_gaze=settings.deep_gaze_enabled, low_power=settings.low_power)
    # The calibration session may still be releasing the webcam.
    for attempt in range(1, CAMERA_START_ATTEMPTS + 1):
        try:
            tracker.start()
            return tracker
        except RuntimeError as exc:
            logger.warning("Camera start attempt %d failed: %s", attempt, exc)
            if attempt == CAMERA_START_ATTEMPTS:
                raise
            time.sleep(1.0)
    return tracker


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="IrisClick background eye-tracking worker")
    parser.add_argument("--profile-id", help="calibration profile id (default: newest)")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings)
    enable_dpi_awareness()

    profile, model = load_profile(settings.profiles_dir, args.profile_id)
    if model is None:
        logger.error("No usable calibration profile; opening the calibration page")
        webbrowser.open(f"{settings.site_url.rstrip('/')}/calibration")
        return 2

    pid_file = PidFile(settings)
    if not pid_file.claim(profile.id):
        logger.info("Another tracking worker is already running")
        return 0
    camera_index = (profile.camera_index if profile.camera_index is not None
                    else get_camera_service().preferred_camera())
    try:
        tracker = start_tracker(settings, camera_index)
    except RuntimeError as exc:
        logger.error("Camera %d could not start: %s", camera_index, exc)
        pid_file.release()
        return 1

    logger.info("Tracking with profile %s on camera %d (%s, per-dot error %.3f, deep gaze %s)",
                profile.id, camera_index, model.feature_source, profile.accuracy_fraction,
                "on" if tracker.deep_gaze_available else "off")
    try:
        TrackingWorker(settings, tracker, model, pid_file).run()
    finally:
        try:
            tracker.stop()
        except RuntimeError as exc:
            logger.warning("Camera stop was slow: %s", exc)
        pid_file.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
