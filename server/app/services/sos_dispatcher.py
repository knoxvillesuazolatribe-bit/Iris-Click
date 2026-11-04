"""Sends SOS alerts in the background, retrying temporary failures.

The SOS request returns as soon as the pending sos_history rows exist; a
daemon thread then sends each one. Retryable failures (e.g. no internet)
are tried again after RETRY_DELAYS_S; others fail at once with the reason.
The page polls the rows, so it always shows the real status.
"""

import logging
import threading
import time
from collections.abc import Callable

from app.config import get_settings
from app.models import database
from app.models.sos import SOS_FAILED, SOS_PENDING, SOS_SENT, SosHistory
from app.models.timestamps import utc_now
from app.services.sos_delivery import DeliveryError, EmailSender, NotConfiguredSms
from app.services.system_log_service import log_activity

logger = logging.getLogger("irisclick.sos")

RETRY_DELAYS_S = (10.0, 30.0, 60.0)
CHANNEL_EMAIL = "email"
CHANNEL_SMS = "sms"


class SosDispatcher:
    def __init__(self, delays: tuple[float, ...] = RETRY_DELAYS_S, inline: bool = False):
        self.delays = delays
        # Tests run sends inline (no thread) with no delays.
        self.inline = inline
        self.email_factory: Callable = lambda: EmailSender(get_settings())
        self.sms_factory: Callable = NotConfiguredSms
        self.sleep: Callable[[float], None] = time.sleep
        self._active: set[int] = set()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    @property
    def max_attempts(self) -> int:
        return 1 + len(self.delays)

    def is_active(self, row_id: int) -> bool:
        with self._lock:
            return row_id in self._active

    def submit(self, activation_id: str, row_ids: list[int], user_id: int, user_name: str) -> None:
        with self._lock:
            self._active.update(row_ids)
        if self.inline:
            self._run(activation_id, row_ids, user_id, user_name)
            return
        thread = threading.Thread(target=self._run, name=f"sos-{activation_id[:8]}", daemon=True,
                                  args=(activation_id, row_ids, user_id, user_name))
        with self._lock:
            self._threads = [t for t in self._threads if t.is_alive()] + [thread]
        thread.start()

    def wait_idle(self, timeout: float = 10.0) -> None:
        with self._lock:
            threads = list(self._threads)
        for thread in threads:
            thread.join(timeout)

    def _run(self, activation_id: str, row_ids: list[int], user_id: int, user_name: str) -> None:
        pending = list(row_ids)
        try:
            for attempt in range(1, self.max_attempts + 1):
                if attempt > 1:
                    self.sleep(self.delays[attempt - 2])
                email, sms = self.email_factory(), self.sms_factory()
                pending = [row_id for row_id in pending
                           if self._attempt(row_id, attempt, email, sms) == "retry"]
                if not pending:
                    break
            self._log_summary(activation_id, user_id, user_name)
        except Exception:  # noqa: BLE001 - a background thread must never die silently
            logger.exception("SOS sending stopped unexpectedly (activation %s)", activation_id)
        finally:
            with self._lock:
                self._active.difference_update(row_ids)

    def _attempt(self, row_id: int, attempt: int, email, sms) -> str:
        last = attempt >= self.max_attempts
        try:
            with database.get_session_factory()() as db:
                row = db.get(SosHistory, row_id)
                if row is None or row.status != SOS_PENDING:
                    return "done"
                channel = email if row.channel == CHANNEL_EMAIL else sms
                subject = row.message_sent.splitlines()[0]
                try:
                    channel.send(row.recipient, subject, row.message_sent)
                except DeliveryError as exc:
                    if exc.retryable and not last:
                        row.error_detail = (f"Not sent yet, retrying (attempt {attempt} of "
                                            f"{self.max_attempts} failed). {exc.message}")
                        db.commit()
                        return "retry"
                    row.status = SOS_FAILED
                    row.error_detail = exc.message + (
                        f" Gave up after {self.max_attempts} attempts." if exc.retryable else "")
                    db.commit()
                    return "done"
                row.status = SOS_SENT
                row.error_detail = None
                row.date_sent = utc_now()
                db.commit()
                return "done"
        except Exception:  # noqa: BLE001 - e.g. the database is briefly unreachable
            logger.exception("SOS attempt %s for row %s failed", attempt, row_id)
            return "done" if last else "retry"

    @staticmethod
    def _log_summary(activation_id: str, user_id: int, user_name: str) -> None:
        with database.get_session_factory()() as db:
            rows = db.query(SosHistory).filter(SosHistory.activation_id == activation_id).all()
            sent = sum(r.status == SOS_SENT for r in rows)
            failed = sum(r.status == SOS_FAILED for r in rows)
            log_activity("sos_delivery",
                         f"SOS alerts for {user_name}: {sent} sent, {failed} failed",
                         user_id, session=db)
            db.commit()


dispatcher = SosDispatcher()
