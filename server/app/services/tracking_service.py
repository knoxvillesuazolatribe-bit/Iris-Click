"""Lifecycle of the background tracking worker process.

The worker owns the webcam while it runs, so it must be stopped before a new
calibration opens the camera. It records itself in a pid file (so a worker
started outside this server is still found) and exits gracefully when the
stop-request file appears, which also removes its tray icon cleanly.
"""

import ctypes
import json
import logging
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from app.config import SERVER_DIR, Settings, get_settings
from app.core.calibration.profile import load_profile
from app.schemas.tracking import WorkerStatusRead

logger = logging.getLogger("irisclick.tracking_service")

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
STILL_ACTIVE = 259
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
GRACEFUL_STOP_TIMEOUT_S = 6.0

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
_kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def pid_alive(pid: int) -> bool:
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        return bool(_kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == STILL_ACTIVE
    finally:
        _kernel32.CloseHandle(handle)


def _terminate(pid: int):
    handle = _kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if handle:
        try:
            _kernel32.TerminateProcess(handle, 1)
        finally:
            _kernel32.CloseHandle(handle)


def stop_request_path(pid_path: Path) -> Path:
    return pid_path.with_suffix(".stop")


class TrackingService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._pid_path = settings.worker_pid_path
        self._stop_path = stop_request_path(self._pid_path)

    def _read_pid_file(self) -> dict | None:
        try:
            data = json.loads(self._pid_path.read_text("utf-8"))
            return data if isinstance(data, dict) and isinstance(data.get("pid"), int) else None
        except (OSError, ValueError):
            return None

    def status(self) -> WorkerStatusRead:
        data = self._read_pid_file()
        if data is None or not pid_alive(data["pid"]):
            return WorkerStatusRead(running=False)
        return WorkerStatusRead(
            running=True,
            pid=data["pid"],
            profile_id=data.get("profile_id"),
            started_at=data.get("started_at"),
        )

    def start(self, profile_id: str | None = None) -> WorkerStatusRead:
        current = self.status()
        if current.running:
            if profile_id is None or profile_id == current.profile_id:
                return current
            self.stop()
        profile, _model = load_profile(self._settings.profiles_dir, profile_id)
        if profile is None:
            raise LookupError("No usable calibration profile. Calibrate first.")

        self._stop_path.unlink(missing_ok=True)
        # pythonw.exe: a background app with no console window.
        executable = Path(sys.executable)
        windowless = executable.with_name("pythonw.exe")
        process = subprocess.Popen(
            [str(windowless if windowless.is_file() else executable),
             "-m", "app.workers.tracking_worker", "--profile-id", profile.id],
            cwd=SERVER_DIR,
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
            close_fds=True,
        )
        logger.info("Tracking worker started (pid=%s, profile=%s)", process.pid, profile.id)
        return WorkerStatusRead(running=True, pid=process.pid, profile_id=profile.id,
                                started_at=datetime.now().astimezone())

    def stop(self) -> WorkerStatusRead:
        data = self._read_pid_file()
        if data is None or not pid_alive(data["pid"]):
            self._pid_path.unlink(missing_ok=True)
            return WorkerStatusRead(running=False)
        pid = data["pid"]
        self._stop_path.write_text("stop", encoding="utf-8")
        deadline = time.monotonic() + GRACEFUL_STOP_TIMEOUT_S
        while time.monotonic() < deadline and pid_alive(pid):
            time.sleep(0.1)
        if pid_alive(pid):
            logger.warning("Tracking worker %s did not stop gracefully; terminating", pid)
            _terminate(pid)
            time.sleep(0.5)
        self._stop_path.unlink(missing_ok=True)
        self._pid_path.unlink(missing_ok=True)
        return WorkerStatusRead(running=False, message="Tracking worker stopped.")


@lru_cache
def get_tracking_service() -> TrackingService:
    return TrackingService(get_settings())
