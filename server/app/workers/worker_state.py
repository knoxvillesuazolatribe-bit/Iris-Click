"""Live tracking status shared with the site's Gaze Tracking page.

The tracking worker runs in its own process. It notes its status line, the
cursor position and wink counts here, and at most every WRITE_EVERY_S they are
written to a small JSON file next to the worker's PID file. The server reads
that file (read_state) for GET /api/me/tracking.

Nothing here may slow down or break tracking: write failures are ignored and
the worker calls every method inside contextlib.suppress.
"""

import json
import os
import time
from pathlib import Path

from app.config import Settings

FILE_NAME = "tracking_worker_state.json"
WRITE_EVERY_S = 0.25
# The worker notes its status on nearly every frame; older data means it hung.
STALE_AFTER_S = 3.0
# The cursor is hidden while the face is lost or tracking is paused.
GAZE_FRESH_S = 1.5


def state_path(settings: Settings) -> Path:
    return settings.worker_pid_path.with_name(FILE_NAME)


class LiveState:
    def __init__(self, settings: Settings, clock=time.time):
        self.path = state_path(settings)
        self._clock = clock
        self._pid = os.getpid()
        self._status = ""
        self._kind = ""
        self._paused = False
        self._gaze: dict | None = None
        self._winks = {"left": 0, "right": 0}
        self._last_write = float("-inf")

    def note_status(self, text: str, kind: str, paused: bool) -> None:
        self._status, self._kind, self._paused = text, kind, paused
        self._write()

    def note_gaze(self, x: float, y: float, screen_w: int, screen_h: int) -> None:
        self._gaze = {"x": round(x), "y": round(y), "screen_w": screen_w,
                      "screen_h": screen_h, "at": self._clock()}
        self._write()

    def note_wink(self, side: str) -> None:
        if side in self._winks:
            self._winks[side] += 1
            self._write(force=True)

    def snapshot(self) -> dict:
        return {"pid": self._pid, "updated_at": self._clock(), "status": self._status,
                "kind": self._kind, "paused": self._paused, "gaze": self._gaze,
                "winks": dict(self._winks)}

    def _write(self, force: bool = False) -> None:
        now = self._clock()
        if not force and now - self._last_write < WRITE_EVERY_S:
            return
        self._last_write = now
        temp = self.path.with_suffix(".tmp")
        try:
            temp.write_text(json.dumps(self.snapshot()), encoding="utf-8")
            os.replace(temp, self.path)
        except OSError:
            # The server may be reading the file right now; try on the next note.
            pass


def read_state(path: Path, pid: int, now: float | None = None) -> dict | None:
    """The live state written by worker ``pid``, or None if missing or stale.

    ``gaze`` is None when the cursor has not moved recently (face lost, paused).
    """
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("pid") != pid:
        return None
    now = time.time() if now is None else now
    updated_at = data.get("updated_at")
    if not isinstance(updated_at, (int, float)) or now - updated_at > STALE_AFTER_S:
        return None
    gaze = data.get("gaze")
    if not isinstance(gaze, dict) or now - gaze.get("at", 0) > GAZE_FRESH_S:
        gaze = None
    winks = data.get("winks") if isinstance(data.get("winks"), dict) else {}
    return {
        "status": str(data.get("status") or ""),
        "kind": str(data.get("kind") or ""),
        "paused": bool(data.get("paused")),
        "gaze": gaze,
        "winks": {"left": int(winks.get("left", 0)), "right": int(winks.get("right", 0))},
    }
