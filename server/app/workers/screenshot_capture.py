"""Both-eye blink screenshot (team decision D2), called from tracking_worker hooks.

Only a deliberate closure counts: the blink detector already ignores closures
under 0.35 s (natural blinks), and closures over MAX_CLOSURE_S are the user
resting their eyes. Grabbing, PNG encoding and the database row happen on a
background thread so the cursor never stutters.
"""

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.config import Settings
from app.models import database
from app.models.calibration_record import CalibrationRecord
from app.models.screenshot import ScreenshotHistory
from app.services import active_user
from app.services.system_log_service import log_activity

logger = logging.getLogger("irisclick.worker.screenshot")

COOLDOWN_S = 2.0
MAX_CLOSURE_S = 1.5
UNASSIGNED = "unassigned"
SAVED = "Screenshot saved"


def _grab_primary_screen():
    from PIL import ImageGrab  # Pillow ships with pyautogui

    return ImageGrab.grab()


class ScreenshotTaker:
    def __init__(self, settings: Settings, profile_id: str | None = None,
                 notify: Callable[[str], None] | None = None,
                 grab: Callable = _grab_primary_screen, background: bool = True):
        self.folder = Path(settings.screenshots_dir)
        self.profile_id = profile_id
        self.notify = notify
        self.grab = grab
        self.background = background
        self._closed_since: float | None = None
        self._last_closure_s = 0.0
        self._last_shot = float("-inf")
        self._threads: list[threading.Thread] = []

    def observe(self, eyes_closing: bool, now: float) -> None:
        """Every frame: times the current closure (the detector reports it on reopening)."""
        if eyes_closing:
            if self._closed_since is None:
                self._closed_since = now
        elif self._closed_since is not None:
            self._last_closure_s = now - self._closed_since
            self._closed_since = None

    def on_both_blink(self, now: float) -> bool:
        """The detector saw a both-eye blink; True if a screenshot was started."""
        if self._last_closure_s > MAX_CLOSURE_S:
            logger.info("Both eyes closed %.1f s: resting, no screenshot", self._last_closure_s)
            return False
        if now - self._last_shot < COOLDOWN_S:
            return False
        self._last_shot = now
        when = datetime.now().astimezone()
        if not self.background:
            self._save(when)
            return True
        thread = threading.Thread(target=self._save, args=(when,), name="screenshot", daemon=True)
        self._threads = [t for t in self._threads if t.is_alive()] + [thread]
        thread.start()
        return True

    def wait_idle(self, timeout: float = 10.0) -> None:
        for thread in list(self._threads):
            thread.join(timeout)

    def _save(self, when: datetime) -> Path | None:
        user_id = active_user.read_from_disk()
        folder = self.folder / (str(user_id) if user_id is not None else UNASSIGNED)
        name = f"{when:%Y-%m-%d_%H-%M-%S}-{when.microsecond // 1000:03d}.png"
        path = folder / name
        try:
            folder.mkdir(parents=True, exist_ok=True)
            self.grab().save(path, format="PNG")
        except Exception:  # noqa: BLE001
            logger.exception("Screenshot could not be saved")
            self._tell("Screenshot failed: it could not be saved")
            return None
        recorded = self._record(user_id, name, path)
        self._tell(SAVED if recorded else f"{SAVED} (not added to your history)")
        logger.info("Screenshot saved: %s", path)
        return path

    def _record(self, user_id: int | None, name: str, path: Path) -> bool:
        try:
            with database.get_session_factory()() as db:
                calibration_id = None
                if self.profile_id:
                    calibration_id = db.scalar(
                        select(CalibrationRecord.calibration_id)
                        .where(CalibrationRecord.profile_file_id == self.profile_id))
                db.add(ScreenshotHistory(user_id=user_id, calibration_id=calibration_id,
                                         file_name=name, file_path=str(path.resolve())))
                log_activity("screenshot", f"Screenshot saved: {name}", user_id, session=db)
                db.commit()
            return True
        except Exception:  # noqa: BLE001 - the file is saved even if the database is down
            logger.exception("Screenshot row not recorded")
            return False

    def _tell(self, text: str) -> None:
        if self.notify is not None:
            try:
                self.notify(text)
            except Exception:  # noqa: BLE001
                pass
