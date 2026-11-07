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
import contextlib
import json
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler

from app.config import Settings, get_settings
from app.core.actions.dwell_click import DwellClicker
from app.core.actions.mouse_controller import MouseController
from app.core.calibration.posture import PostureMonitor
from app.core.calibration.profile import load_profile
from app.core.calibration.recenter import (
    RECENTER_POINTS,
    RecenterSession,
    load_recenter_record,
    save_recenter,
)
from app.core.gaze.screen_mapper import ScreenCorrection
from app.core.detection.blink_detector import BOTH, LEFT, RIGHT, BlinkDetector
from app.core.detection.iris_detector import distance_advice
from app.core.detection.lighting import LIGHTING_GUIDANCE
from app.core.gaze.estimator import GazeTracker
from app.core.gaze.blink_anchor import BlinkAnchor
from app.core.gaze.diagnostics import Diagnostics
from app.core.gaze.edge_reach import next_edge_level
from app.core.gaze.feature_sources import required_engines
from app.core.gaze.navigation import CursorNavigator, NavigationConfig
from app.core.gaze.pipeline import TRANSIENT_REASONS, GazePipeline
from app.core.gaze.smoothing import CursorGlide
from app.desktop.camera_preview import PREVIEW_WIDTH, CameraPreview
from app.desktop.display import enable_dpi_awareness
from app.desktop.gaze_overlay import GazeOverlay
from app.desktop.main_window import ControlBar
from app.desktop.system_tray import (
    CYCLE_EDGE,
    FORWARD,
    HOME,
    KEYBOARD,
    NEXT_TAB,
    PAUSE,
    QUIT,
    RECALIBRATE,
    RECENTER,
    TOGGLE_PREVIEW,
    TOGGLE_VOICE,
    SystemTray,
)
from app.desktop.target_assist import TargetFinder, tk_button_targets
from app.desktop.voice import Speaker, VoiceGuide
from app.services.camera_service import (
    get_camera_service,
    read_device_settings,
    update_device_settings,
)
from app.services.tracking_service import pid_alive, stop_request_path

try:  # Phase 3 hook: live status for the site's Gaze Tracking page (optional).
    from app.workers.worker_state import LiveState
except Exception:  # noqa: BLE001
    LiveState = None
try:  # Phase 6 hooks: screenshot, edge scroll, Forward / Next Tab (optional).
    from app.workers import extra_keys
    from app.workers.worker_extras import WorkerExtras
except Exception:  # noqa: BLE001
    extra_keys = WorkerExtras = None
try:  # Phase 7 hook (H4d): the signed-in user's accessibility settings (optional).
    from app.workers import user_settings
except Exception:  # noqa: BLE001
    user_settings = None

TICK_MS = 20
STOP_CHECK_EVERY_TICKS = 25
TOPMOST_EVERY_TICKS = 100
LOCAL_TARGETS_EVERY_TICKS = 50
CAMERA_RETRY_S = 3.0
CAMERA_START_ATTEMPTS = 4
# Eyes re-settle for a moment after reopening; hold the cursor meanwhile.
POST_BLINK_HOLD_S = 0.3
# Non-legacy modes show the glide one tick ahead: CursorGlide.position at the
# instant set_target is called is still the previous point, which delays every
# new estimate by a full tick.
GLIDE_LEAD_S = TICK_MS / 1000.0
# Length of the cursor path drawn while the camera preview is on.
TRAIL_S = 1.0

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
POSTURE_TEXT = {
    "distance": "You moved nearer or farther since calibration. Choose Re-centre.",
    "angle": "Your head turned since calibration. Choose Re-centre.",
}
POSTURE_SPEECH = ("You are sitting differently from when the aim was set. "
                  "Choose Re-centre to fix it, or sit as before.")

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
    def __init__(self, settings: Settings, tracker: GazeTracker, model, pid_file: PidFile,
                 profile_id: str | None = None, posture=None):
        """``posture``: PostureReference the active mapping was fitted in, or None."""
        self.settings = settings
        self.tracker = tracker
        self.model = model
        self.pid_file = pid_file
        self.profile_id = profile_id
        self.posture = PostureMonitor(posture)
        self.recenter: RecenterSession | None = None
        self._correction_before_recenter = None
        self.mouse = MouseController()
        self.screen_w, self.screen_h = self.mouse.screen_size()

        self.commands: queue.Queue[str] = queue.Queue()
        self.root = tk.Tk()
        self.root.title("IrisClick")
        self.overlay = GazeOverlay(self.root, self.screen_w, self.screen_h)
        self.bar = ControlBar(self.root, self.commands, self.screen_w)
        self.preview = CameraPreview(self.root, self.screen_w, self.screen_h)
        self.tray = SystemTray(self.commands)
        self.speaker = Speaker()
        self.voice = VoiceGuide(self.speaker)
        self.voice.enabled = settings.voice_guidance_enabled

        self.pipeline = GazePipeline()
        self.blink = BlinkDetector(threshold=settings.blink_threshold)
        edge_level = read_device_settings(settings).edge_sensitivity or settings.edge_sensitivity
        self.navigator = CursorNavigator(
            NavigationConfig.from_settings(settings, edge_sensitivity=edge_level),
            self.screen_w, self.screen_h)
        self.bar.set_edge_level(edge_level)
        self.tray.set_edge_level(edge_level)
        self._glide_lead = 0.0 if self.navigator.config.mode == "legacy" else GLIDE_LEAD_S
        self.glide = CursorGlide()
        self.dwell = DwellClicker(radius_px=settings.dwell_radius_px, dwell_ms=settings.dwell_ms,
                                  cooldown_ms=settings.dwell_cooldown_ms)
        self.dwell_enabled = settings.dwell_click_enabled
        self.targets = TargetFinder()
        self.diagnostics = Diagnostics(settings.diagnostics_enabled,
                                       settings.diagnostics_interval_s,
                                       settings.diagnostics_trace_path)
        self._last_frame_id = 0
        self._last_tick_at = None
        self._target = None
        self._fine_aim = False
        self._fine_aim_announced = False
        self._handoff_until = 0.0
        self._handoff_pos = None
        self.blink_anchor = BlinkAnchor()
        self._lid_down = False
        self._wink_point = None
        self._hold_until = 0.0
        self.paused = False
        self._pause_reason = ""
        self._was_paused = False
        self._showing_cursor = False
        self._tick_count = 0
        self._trail: deque[tuple[float, float, float]] = deque()
        self._raw_point = None
        self._set_preview(settings.camera_preview_enabled)
        logger.info("Gaze navigation mode: %s", self.navigator.config.mode)
        self._camera_restart: threading.Thread | None = None
        self._next_camera_retry = 0.0
        self._quitting = False
        # Phase 3 hook: live status for the site. Tracking works without it.
        self._live = None
        with contextlib.suppress(Exception):
            self._live = LiveState(settings)
        # Phase 6 hooks (H4a/H4c): screenshot and edge scroll. Tracking works without them.
        self._extras = None
        with contextlib.suppress(Exception):
            self._extras = WorkerExtras(self.root, self.bar.win, settings, profile_id,
                                        self.screen_w, self.screen_h, self.voice.announce)

    def run(self):
        self.tray.start()
        self.speaker.start()
        if self.navigator.config.uses_targets:
            self.targets.start()
        self.voice.announce("Eye tracking is on.", time.monotonic())
        self.root.after(TICK_MS, self._tick)
        try:
            self.root.mainloop()
        finally:
            self.tray.stop()
            self.speaker.stop()
            self.targets.stop()
            self.diagnostics.close()

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
        with contextlib.suppress(Exception):  # Phase 3 hook: live status
            self._live.note_status(text, kind, self.paused)

    def _pause(self, reason: str):
        self.paused = True
        self._pause_reason = reason
        self._reset_motion()
        logger.info("Tracking paused: %s", reason)
        self.voice.announce(f"Tracking paused. {reason} Choose Resume to continue.",
                            time.monotonic())

    def _reset_motion(self):
        self.pipeline.reset()
        self.navigator.reset()
        self.glide.reset()
        self.dwell.reset()
        self.blink_anchor.reset()
        self._wink_point = None
        self._target = None
        self._fine_aim = False
        self._showing_cursor = False
        self._trail.clear()
        self._raw_point = None
        self.mouse.forget_position()

    def _set_preview(self, enabled: bool):
        """Camera preview window plus the eyes-to-cursor line on the overlay."""
        self.preview.set_visible(enabled)
        # Only pay for the downscaled frame while someone is looking at it.
        self.tracker.preview_width = PREVIEW_WIDTH if enabled else None
        self.bar.set_preview(enabled)
        self.tray.set_preview(enabled)
        if not enabled:
            self.overlay.hide_link()
            self._trail.clear()

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
            gaze_sent = self.mouse.last_sent
            self._handoff_pos = self.mouse.position()
            self._handoff_until = now + self.settings.mouse_handoff_s
            self._reset_motion()
            # Positions show whether a hand-off was a real mouse move or a
            # false trigger (each one pauses gaze for mouse_handoff_s).
            logger.info("Physical mouse in use; gaze handed off (cursor %s, gaze sent %s)",
                        self._handoff_pos, gaze_sent)
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
            elif command == RECENTER:
                self._toggle_recenter(now)
            elif command == TOGGLE_PREVIEW:
                self._set_preview(not self.preview.visible)
            elif command == CYCLE_EDGE:
                self._cycle_edge(now)
            elif command == RECALIBRATE:
                webbrowser.open(f"{self.settings.site_url.rstrip('/')}/calibration")
                self.quit()
            elif command == QUIT:
                self.quit()
            elif command == HOME:  # H3: open the Home Suite; tracking keeps running
                with contextlib.suppress(Exception):
                    webbrowser.open(f"{self.settings.site_url.rstrip('/')}/home")
            elif command in (FORWARD, NEXT_TAB):  # H3 (Phase 6): Alt+Right / Ctrl+Tab
                with contextlib.suppress(Exception):
                    extra_keys.press(command)
            elif command == KEYBOARD:  # H3 (Phase 9): open/close the on-screen keyboard
                with contextlib.suppress(Exception):
                    self._extras.toggle_keyboard()

    def _cycle_edge(self, now: float):
        level = next_edge_level(self.navigator.config.edge_sensitivity)
        self.navigator.set_edge_sensitivity(level)
        self.bar.set_edge_level(level)
        self.tray.set_edge_level(level)
        update_device_settings(self.settings, edge_sensitivity=level)
        self.voice.announce(f"Edge sensitivity {level}.", now)

    def _hide(self, text: str, kind: str):
        self.overlay.hide_cursor()
        self._showing_cursor = False
        self._set_status(text, kind)

    def _tick(self):
        if self._quitting:
            return
        self._tick_count += 1
        started = time.perf_counter()
        if self._last_tick_at is not None:
            self.diagnostics.record("tick_interval", (started - self._last_tick_at) * 1000.0)
        self._last_tick_at = started
        try:
            self._step()
        except Exception as exc:
            logger.exception("Tracking step failed: %s", exc)
            self._pause("Something went wrong.")
        finished = time.perf_counter()
        self.diagnostics.record("tick", (finished - started) * 1000.0)
        self.diagnostics.maybe_report(finished)
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
            self.preview.keep_on_top()
        if self._tick_count % LOCAL_TARGETS_EVERY_TICKS == 1:
            local_targets = tk_button_targets(self.bar.win)
            with contextlib.suppress(Exception):  # Phase 9: on-screen keyboard keys snap too
                local_targets = local_targets + self._extras.keyboard_targets()
            self.targets.set_local_targets(local_targets)
        now_s = time.monotonic()

        # A re-centre needs no cursor, and clicking its button with the real
        # mouse must not pause the dots it just started.
        if not self.paused and self.recenter is None and self._mouse_in_use(now_s):
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
        if reading.frame_id != self._last_frame_id:
            self._last_frame_id = reading.frame_id
            self.diagnostics.count("frames")
            self.diagnostics.count("dropped_frames", reading.dropped)
            self.diagnostics.record_many(reading.timings, "tracker.")
            # Shown even without a face: framing the face is what it is for.
            self.preview.show(reading)
        estimate = self.pipeline.process(reading, self.model, self.settings.cursor_smoothing,
                                         output_size=(self.screen_w, self.screen_h))
        reason = self.pipeline.reason
        lighting = LIGHTING_GUIDANCE.get(reading.lighting_status)
        distance = distance_advice(reading.eye_line) if reading.face_found else None
        # Also fed during a re-centre: its frames become the new reference.
        if (self.posture.update(now_s, reading) and self.recenter is None
                and not self.paused):
            logger.info("Posture changed (%s) since the mapping was fitted", self.posture.change)
            self.voice.announce(POSTURE_SPEECH, now_s)

        if self.recenter is not None:
            self._step_recenter(estimate, reason, now_s)
            return

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

        eye_closing = self.blink.classify(reading.left_ear, reading.right_ear) is not None
        with contextlib.suppress(Exception):  # H4a: time closures (long = resting eyes)
            self._extras.observe_closure(eye_closing, now_s)
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
            self.navigator.reset_fixation()
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

        config = self.navigator.config
        targets = self.targets.targets() if config.uses_targets else ()
        step = self.navigator.update(estimate, reading, targets, now_s)
        x, y, self._target = step.x, step.y, step.target
        self._fine_aim = step.fine
        if step.fine and not self._fine_aim_announced:
            self._fine_aim_announced = True
            self.voice.announce("Fine aim. Keep your eyes still and move your head slightly "
                                "to adjust. Wink left to click.", now_s)
        self._raw_point = (min(max(estimate.raw_x, 0.0), self.screen_w - 1.0),
                           min(max(estimate.raw_y, 0.0), self.screen_h - 1.0))

        if not config.glides:
            self.glide.reset()
        self.glide.set_target(x, y, now)
        gx, gy = self.glide.position(now + self._glide_lead)
        nav_done = time.perf_counter()
        self.mouse.move(gx, gy, force=True)
        moved = time.perf_counter()
        self._record_cursor(reading, estimate, step, (gx, gy), now, nav_done, moved)
        if self.dwell_enabled and self.dwell.update(x, y):
            self.mouse.left_click(x, y)
            self.glide.reset()
            self.glide.set_target(x, y, now)
            gx, gy = x, y
        self._draw(gx, gy, DISTANCE_TEXT.get(distance) or POSTURE_TEXT.get(self.posture.change))
        with contextlib.suppress(Exception):  # H4c: edge-dwell scroll
            self._extras.cursor_drawn(gx, gy, now_s)
        self.blink_anchor.record(now_s, gx, gy, reading.left_ear, reading.right_ear)

    def _record_cursor(self, reading, estimate, step, shown, started, nav_done, moved):
        """``started``/``nav_done``/``moved``: perf_counter around navigation and the OS move."""
        diagnostics = self.diagnostics
        if not diagnostics.enabled:
            return
        diagnostics.count("cursor_updates")
        diagnostics.record("navigate", (nav_done - started) * 1000.0)
        diagnostics.record("mouse_move", (moved - nav_done) * 1000.0)
        # Software latency only: camera read return -> OS cursor set.
        diagnostics.record("capture_to_cursor", (moved - reading.captured_at) * 1000.0)
        if step.target is not None:
            diagnostics.count("snapped")
        if self.navigator.config.uses_head:
            diagnostics.record("head_offset_px", step.head_offset_px)
        diagnostics.trace({
            "t": round(reading.captured_at, 4), "frame": reading.frame_id,
            "raw": [round(estimate.raw_x, 1), round(estimate.raw_y, 1)],
            "pipeline": [round(estimate.x, 1), round(estimate.y, 1)],
            "cursor": [round(step.x, 1), round(step.y, 1)],
            "shown": [round(shown[0], 1), round(shown[1], 1)],
            "head_px": round(step.head_offset_px, 1), "snapped": step.target is not None,
            "age_ms": round((moved - reading.captured_at) * 1000.0, 1),
            "tracker_ms": reading.timings,
        })

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
        position = self.glide.position(now + self._glide_lead)
        if position is None:
            return
        self.mouse.move(*position)
        self.overlay.show_cursor(*position, self._dwell_progress(), self._target_rect(),
                                 self._fine_aim)
        self._draw_link(*position)

    def _draw_link(self, x: float, y: float, new_frame: bool = False):
        if not self.preview.visible:
            return
        if new_frame:
            now = time.monotonic()
            self._trail.append((now, x, y))
            while self._trail and now - self._trail[0][0] > TRAIL_S:
                self._trail.popleft()
        trail = [(tx, ty) for _, tx, ty in self._trail] + [(x, y)]
        self.overlay.show_link(self.preview.eye_point_on_screen(), (x, y), trail, self._raw_point)

    def _dwell_progress(self) -> float:
        return self.dwell.progress() if self.dwell_enabled else 0.0

    def _target_rect(self):
        t = self._target
        return (t.left, t.top, t.right, t.bottom) if t is not None else None

    def _draw(self, x: float, y: float, warning: str | None):
        self.overlay.show_cursor(x, y, self._dwell_progress(), self._target_rect(),
                                 self._fine_aim)
        self._draw_link(x, y, new_frame=True)
        self._showing_cursor = True
        with contextlib.suppress(Exception):  # Phase 3 hook: live gaze position
            self._live.note_gaze(x, y, self.screen_w, self.screen_h)
        if warning:
            self._set_status(warning, "problem")
        elif self._target is not None:
            self._set_status(f"Target: {self._target.name[:30] or 'button'}. Wink left to click.",
                             "tracking")
        elif self._fine_aim:
            self._set_status("Fine aim: move your head slightly. Wink left to click.", "tracking")
        else:
            source = "landmark fallback" if self.pipeline.using_reference_model else "Tracking"
            self._set_status(source, "tracking")

    def _handle_blink(self, reading):
        side = self.blink.update(reading.left_ear, reading.right_ear)
        if side is None or self.paused:
            return
        with contextlib.suppress(Exception):  # Phase 3 hook: live wink counter
            self._live.note_wink(side)
        if self.settings.swap_blink_sides:
            side = {LEFT: RIGHT, RIGHT: LEFT}.get(side, side)
        if side == LEFT and not getattr(self.settings, "blink_click_enabled", True):
            side = None  # H4d: the user turned wink-to-click off (dwell click is on)
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
        elif side == BOTH:  # H4a/H4b: once = screenshot, twice = on-screen keyboard
            with contextlib.suppress(Exception):
                logger.info("Both-eye blink: %s", self._extras.both_blink(time.monotonic()))
        self.dwell.reset()

    def _toggle_recenter(self, now: float):
        """Start the 5-dot re-centre, or cancel one in progress."""
        if self.recenter is not None:
            self._finish_recenter(None, "Re-centre cancelled.")
            return
        if self.model is None or not hasattr(self.model, "set_correction"):
            return
        # Dots are fitted against the uncorrected mapping; restored on failure.
        self._correction_before_recenter = self.model.correction
        self.model.set_correction(None)
        self._reset_motion()
        self.overlay.hide_cursor()
        self.recenter = RecenterSession(now)
        self.bar.set_recentering(True)
        logger.info("Re-centre started")
        self.voice.announce("Re-centre. Look at each yellow dot until its ring fills.", now)

    def _step_recenter(self, estimate, reason, now: float):
        session = self.recenter
        prediction = None
        # Only fresh open-eye frames count; a frame is offered once (duplicates
        # and blinks give no estimate).
        if estimate is not None and reason is None:
            prediction = (estimate.raw_x / self.screen_w, estimate.raw_y / self.screen_h)
        session.update(now, prediction)
        if session.error is not None:
            self._finish_recenter(None, f"Re-centre failed. {session.error}")
            return
        if session.finished:
            try:
                correction, residual = session.result()
            except ValueError as exc:
                self._finish_recenter(None, f"Re-centre failed. {exc}")
                return
            self._finish_recenter(correction, "Re-centred.", residual)
            return
        tx, ty = session.target
        label = f"{session.index + 1} / {len(RECENTER_POINTS)}"
        self.overlay.show_dot(tx * (self.screen_w - 1), ty * (self.screen_h - 1),
                              session.progress(now), label)
        self._set_status(f"Re-centre: look at dot {label}", "tracking")

    def _finish_recenter(self, correction, message: str, residual: float = 0.0):
        self.recenter = None
        self.bar.set_recentering(False)
        self.overlay.hide_dot()
        if correction is None:
            self.model.set_correction(self._correction_before_recenter)
            logger.info(message)
        else:
            self.model.set_correction(correction)
            # The dots span the whole screen, like the calibration's, so the
            # recent median posture is a fair reference for the new mapping.
            posture = self.posture.current()
            self.posture.set_reference(posture)
            logger.info("Re-centred (residual %.3f): %s, posture %s", residual,
                        [round(v, 3) for v in correction.as_list()], posture)
            if self.profile_id is not None:
                save_recenter(self.settings.recenter_path, self.profile_id, correction, residual,
                              posture)
        self._reset_motion()
        self.voice.announce(message, time.monotonic())

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


def start_tracker(settings: Settings, camera_index: int, model=None) -> GazeTracker:
    pupils, deep = required_engines(model) if model is not None else (True, True)
    # Calibration runs every engine to compare sources; live tracking only
    # needs the chosen one. Unused pupil/MGazeNet passes cost CPU per frame.
    tracker = GazeTracker(settings.face_model_path, camera_index=camera_index,
                          refine_pupils=settings.refine_pupils and pupils,
                          deep_gaze=settings.deep_gaze_enabled and deep,
                          low_power=settings.low_power,
                          camera_backend=settings.camera_backend,
                          camera_fourcc=settings.camera_fourcc,
                          camera_resolution=settings.camera_resolution)
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
    with contextlib.suppress(Exception):  # H4d: per-user settings, .env on any failure
        settings = user_settings.for_active_user(settings)

    profile, model = load_profile(settings.profiles_dir, args.profile_id)
    if model is None:
        logger.error("No usable calibration profile; opening the calibration page")
        webbrowser.open(f"{settings.site_url.rstrip('/')}/calibration")
        return 2
    recentre = load_recenter_record(settings.recenter_path, profile.id)
    posture = profile.posture
    if recentre is not None:
        model.set_correction(ScreenCorrection(recentre.matrix))
        # A re-centre without a stored posture predates tracking; unknown.
        posture = recentre.posture
        logger.info("Applied saved re-centre for profile %s: %s", profile.id,
                    [round(v, 3) for v in recentre.matrix])
    if posture is None:
        logger.info("No posture reference; posture-change prompts are off until a re-centre")

    pid_file = PidFile(settings)
    if not pid_file.claim(profile.id):
        logger.info("Another tracking worker is already running")
        return 0
    camera_index = (profile.camera_index if profile.camera_index is not None
                    else get_camera_service().preferred_camera())
    try:
        tracker = start_tracker(settings, camera_index, model)
    except RuntimeError as exc:
        logger.error("Camera %d could not start: %s", camera_index, exc)
        pid_file.release()
        return 1

    logger.info("Tracking with profile %s on camera %d (%s, per-dot error %.3f, deep gaze %s, "
                "pupil refinement %s)",
                profile.id, camera_index, model.feature_source, profile.accuracy_fraction,
                "on" if tracker.deep_gaze_available else "off",
                "on" if tracker.refine_pupils else "off")
    try:
        TrackingWorker(settings, tracker, model, pid_file, profile.id, posture).run()
    finally:
        try:
            tracker.stop()
        except RuntimeError as exc:
            logger.warning("Camera stop was slow: %s", exc)
        pid_file.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
