"""Runs database writes off the caller's thread, one at a time.

Used where a write must never slow down or break a working feature (a
calibration result, a gaze click): submit() returns at once, and a job that
raises is logged and dropped. The thread is a daemon, so a database that
hangs never keeps the server from exiting.
"""

import logging
import queue
import threading
from collections.abc import Callable

logger = logging.getLogger("irisclick.background_db")


class BackgroundWriter:
    def __init__(self, name: str):
        self._name = name
        self._jobs: queue.Queue[Callable[[], None]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def submit(self, job: Callable[[], None]) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
                self._thread.start()
        self._jobs.put(job)

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Block until every job submitted so far has run; False on timeout."""
        done = threading.Event()
        self.submit(done.set)
        return done.wait(timeout)

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            try:
                job()
            except Exception as exc:
                logger.warning("Background database write failed: %s", exc)
            finally:
                self._jobs.task_done()


writer = BackgroundWriter("irisclick-db-writer")
