"""Steps and timing of the desktop calibration window, with no screen code.

It speaks the existing ``/api/ws/calibration`` protocol exactly like the website's
calibration page (start, then collect one dot at a time) and keeps the same dot
timing (use-calibration-flow.ts), so the engine sees the same session either way.
What differs is the start: there is no working gaze cursor yet, so nothing needs a
click. Once the eyes are steadily registered for STEADY_FACE_S a spoken 3-2-1
countdown starts; a helper can press Enter or Space to start at once.

Inputs:  connected(), on_message(), tick(), key(), cancel(), connection_lost()
Outputs: take_outgoing() for the calibration socket, take_events() for the website
         (via the agent channel), take_speech() for the voice, view() for the window,
         and the flags ``close`` (window should close) and ``restart`` (try again).
"""

import math

CONNECTING, CHECKING, COUNTDOWN, DOTS, FITTING = "connecting", "checking", "countdown", "dots", "fitting"
SUCCESS, FAILED, CANCELLED = "success", "failed", "cancelled"
ACTIVE = (CONNECTING, CHECKING, COUNTDOWN, DOTS, FITTING)

STEADY_FACE_S = 2.0
# Never trapped on the camera check: a visible face starts the countdown after this.
REGISTRATION_MAX_S = 12.0
COUNTDOWN_S = 3
# Same as the website (use-calibration-flow.ts).
FIRST_DOT_SETTLE_S = 0.9
DOT_SETTLE_S = 0.5
RETRY_REST_S = 1.9
ACCEPTED_FLASH_S = 0.6
CLOSE_AFTER_SUCCESS_S = 3.0
CLOSE_AFTER_WARNING_S = 5.0
RETRY_AFTER_FAIL_S = 10.0
CLOSE_AFTER_LOST_S = 5.0

SAY_INTRO = "Look at the centre of the screen. Calibration starts by itself when your eyes are steady."
SAY_DOTS = "Look at each dot. Only move your eyes."
SAY_PAUSED = "Paused. Press Space to continue."
SAY_SUCCESS = "Calibration complete. Eye tracking is starting."
SAY_WARNING = "Calibration saved with low accuracy. Large buttons will work."
SAY_RETRY = "Trying again in ten seconds."
LOST = "Lost the connection to IrisClick Desktop."


def accuracy_percent(error_fraction: float | None) -> float | None:
    """Same formula as the saved record: (1 - per-dot error) x 100, kept within 0-100."""
    if error_fraction is None:
        return None
    return round(min(max((1.0 - float(error_fraction)) * 100.0, 0.0), 100.0), 2)


def advice_for(frame: dict | None) -> tuple[str, str] | None:
    """(kind, text) for what the person should fix now, or None."""
    if not frame:
        return None
    if not frame.get("face_found"):
        return "face", frame.get("guidance") or "We cannot see your face. Face the camera."
    if frame.get("distance_advice"):
        return "distance", frame.get("guidance") or "Adjust your distance from the screen."
    if frame.get("guidance"):
        return "lighting", frame["guidance"]
    if not frame.get("eyes_open"):
        return "eyes", "Open your eyes wide and look at the screen."
    return None


class CalibrationFlow:
    def __init__(self, profile_name: str, screen: tuple[int, int], now: float, auto_retry: bool = True):
        self.profile_name = profile_name[:60]
        self.screen = screen
        self.auto_retry = auto_retry
        self.phase = CONNECTING
        self.points: list[tuple[float, float]] = []
        self.index = 0
        self.collecting = False
        self.accepted_at: float | None = None
        self.rest_until: float | None = None
        self.settle_from = now
        self.paused = False
        self.frame: dict | None = None
        self.steady_since: float | None = None
        self.checking_since = now
        self.countdown_from: float | None = None
        self.countdown_number: int | None = None
        self.advice: tuple[str, str] | None = None
        self.message: str | None = None
        self.result: dict | None = None
        self.finished_at: float | None = None
        self.close = False
        self.restart = False
        self._out: list[dict] = []
        self._events: list[dict] = []
        self._speech: list[str] = []

    # ---- outputs
    def take_outgoing(self) -> list[dict]:
        out, self._out = self._out, []
        return out

    def take_events(self) -> list[dict]:
        out, self._events = self._events, []
        return out

    def take_speech(self) -> list[str]:
        out, self._speech = self._speech, []
        return out

    def _event(self, message_type: str, /, **fields) -> None:
        self._events.append({"v": 1, "type": message_type, **fields})

    @property
    def total(self) -> int:
        return len(self.points) or 13

    @property
    def done(self) -> int:
        return self.index + (1 if self.accepted_at is not None else 0)

    # ---- inputs
    def connected(self, now: float) -> None:
        self._out.append({"type": "start", "profile_name": self.profile_name,
                          "screen": {"width": int(self.screen[0]), "height": int(self.screen[1])}})

    def on_message(self, message: dict, now: float) -> None:
        kind = message.get("type")
        if kind == "ready":
            self.points = [(p["x"], p["y"]) for p in message["points"]]
            self.phase, self.checking_since, self.steady_since = CHECKING, now, None
            self._event("calibration.started", total=self.total)
            self._speech.append(SAY_INTRO)
        elif kind == "frame_status":
            self.frame = message
            advice = advice_for(message)
            if advice != self.advice:
                self.advice = advice
                self._event("calibration.advice", kind=advice[0] if advice else None,
                            text=advice[1] if advice else None)
                if advice and self.phase in (CHECKING, DOTS):
                    self._speech.append(advice[1])
        elif kind == "point_result":
            self.collecting = False
            status = message.get("status")
            if status == "accepted":
                self.accepted_at = now
                self._event("calibration.progress", done=self.done, total=self.total)
                if self.done >= self.total:
                    self.phase = FITTING
            elif status == "retry":
                self.rest_until = now + RETRY_REST_S
                self.message = message.get("message") or "That dot was not clear."
                self._speech.append(self.message)
        elif kind == "result":
            self._finish(message, now)
        elif kind == "error":
            if message.get("fatal"):
                self._fail(message.get("message") or "Calibration stopped.", now)
            else:
                self.message = message.get("message")

    def tick(self, now: float) -> None:
        if self.paused:
            return
        if self.phase == CHECKING:
            registered = bool(self.frame and self.frame.get("registered"))
            self.steady_since = (now if self.steady_since is None else self.steady_since) if registered else None
            face = bool(self.frame and self.frame.get("face_found"))
            if (self.steady_since is not None and now - self.steady_since >= STEADY_FACE_S) or (
                    face and now - self.checking_since >= REGISTRATION_MAX_S):
                self._start_countdown(now)
        elif self.phase == COUNTDOWN:
            elapsed = now - (now if self.countdown_from is None else self.countdown_from)
            if elapsed >= COUNTDOWN_S:
                self._start_dots(now)
            else:
                number = COUNTDOWN_S - math.floor(elapsed)
                if number != self.countdown_number:
                    self.countdown_number = number
                    self._speech.append(str(number))
        elif self.phase == DOTS:
            if self.accepted_at is not None and now - self.accepted_at >= ACCEPTED_FLASH_S:
                self.accepted_at, self.index, self.settle_from = None, self.index + 1, now
            if self.rest_until is not None and now >= self.rest_until:
                self.rest_until, self.message, self.settle_from = None, None, now
            if not (self.collecting or self.accepted_at is not None or self.rest_until is not None) \
                    and self.index < len(self.points):
                settle = FIRST_DOT_SETTLE_S if self.index == 0 else DOT_SETTLE_S
                if now - self.settle_from >= settle:
                    self.collecting = True
                    self._out.append({"type": "collect", "index": self.index})
        elif self.phase == SUCCESS and self.finished_at is not None:
            low = bool(self.result and self.result.get("low_accuracy"))
            if now - self.finished_at >= (CLOSE_AFTER_WARNING_S if low else CLOSE_AFTER_SUCCESS_S):
                self.close = True
        elif self.phase == FAILED and self.finished_at is not None:
            if self.message == LOST:
                if now - self.finished_at >= CLOSE_AFTER_LOST_S:
                    self.close = True
            elif self.auto_retry and now - self.finished_at >= RETRY_AFTER_FAIL_S:
                self.restart = True

    def key(self, name: str, now: float) -> None:
        """Helper keys: "enter", "space", "escape"."""
        if name == "escape":
            self.cancel(now)
        elif self.phase == CHECKING and name in ("enter", "space"):
            self._start_countdown(now)
        elif self.phase == COUNTDOWN and name == "enter":
            self._start_dots(now)
        elif self.phase in (COUNTDOWN, DOTS) and name == "space":
            self.paused = not self.paused
            if self.paused:
                self._speech.append(SAY_PAUSED)
            else:
                self.settle_from = now
                if self.phase == COUNTDOWN:
                    self._start_countdown(now)
        elif self.phase == FAILED and name == "enter" and self.message != LOST:
            self.restart = True
        elif self.phase == SUCCESS and name in ("enter", "space"):
            self.close = True

    def cancel(self, now: float, reason: str = "cancelled") -> None:
        if self.phase in ACTIVE:
            self._out.append({"type": "cancel"})
            self.phase = CANCELLED
            self._event("calibration.cancelled", reason=reason)
        self.close = True

    def connection_lost(self, now: float) -> None:
        if self.phase in ACTIVE:
            self._fail(LOST, now)

    # ---- helpers
    def _start_countdown(self, now: float) -> None:
        self.phase, self.countdown_from, self.countdown_number = COUNTDOWN, now, None
        self._speech.append(SAY_DOTS)

    def _start_dots(self, now: float) -> None:
        self.phase, self.settle_from, self.countdown_number = DOTS, now, None

    def _finish(self, message: dict, now: float) -> None:
        profile = message.get("profile") or {}
        if message.get("status") == "success":
            percent = accuracy_percent(profile.get("accuracy_fraction"))
            low = bool(profile.get("low_accuracy"))
            self.phase, self.finished_at = SUCCESS, now
            self.result = {"status": "success", "accuracy_percent": percent, "low_accuracy": low,
                           "message": message.get("message", "")}
            self._event("calibration.result", **self.result)
            self._speech.append(SAY_WARNING if low else SAY_SUCCESS)
        else:
            self._fail(message.get("message") or "Calibration was not accurate enough.", now)

    def _fail(self, text: str, now: float) -> None:
        self.phase, self.finished_at, self.message, self.collecting = FAILED, now, text, False
        self.result = {"status": "failed", "accuracy_percent": None, "low_accuracy": False, "message": text}
        self._event("calibration.result", **self.result)
        self._speech.append(text if text == LOST or not self.auto_retry else f"{text} {SAY_RETRY}")

    def view(self, now: float) -> dict:
        dot = None
        if self.phase == DOTS and self.index < len(self.points):
            state = ("accepted" if self.accepted_at is not None else "rest" if self.rest_until is not None
                     else "collecting" if self.collecting else "waiting")
            dot = {"x": self.points[self.index][0], "y": self.points[self.index][1], "state": state}
        retry_in = None
        if self.phase == FAILED and self.auto_retry and self.message != LOST and self.finished_at is not None:
            retry_in = max(0, math.ceil(RETRY_AFTER_FAIL_S - (now - self.finished_at)))
        frame = self.frame or {}
        return {
            "phase": self.phase, "paused": self.paused, "dot": dot, "done": self.done, "total": self.total,
            "countdown": self.countdown_number, "advice": self.advice[1] if self.advice else None,
            "checks": {"face": bool(frame.get("face_found")), "eyes": bool(frame.get("eyes_open")),
                       "distance": bool(frame.get("face_found")) and not frame.get("distance_advice")},
            "message": self.message, "result": self.result, "retry_in": retry_in,
        }
