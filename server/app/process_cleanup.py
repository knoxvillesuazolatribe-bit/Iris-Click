"""Close every IrisClick process still running from this install (uninstall / upgrade).

``launcher.stop`` closes the processes whose ids it saved (server and tray launcher, with their
children). A process whose parent crashed or restarted is not in either tree: the eye-tracking
worker, for example, keeps running with no window, and Windows then refuses to uninstall or
replace the IrisClick folder ("the app is running in the background").

This closes what is left, by where the program file lives: only processes started from this
install's own ``runtime`` folder, never the one asking. Nothing happens unless IrisClick runs
from an installed copy (``<install>\\runtime\\python.exe``), so a developer's Python is never
touched.
"""

import ctypes
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

logger = logging.getLogger("irisclick.process_cleanup")

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
CREATE_NO_WINDOW = 0x08000000


def installed_runtime(server_dir: Path, executable: str | Path | None = None) -> Path | None:
    """``<install>\\runtime`` when this Python runs from it, else None (development)."""
    runtime = (Path(server_dir).resolve().parent / "runtime")
    exe = Path(executable or sys.executable).resolve()
    return runtime if exe.parent == runtime and runtime.is_dir() else None


def _running() -> Iterable[tuple[int, str]]:
    """(pid, program path) of every process this user may look at (Windows only)."""
    if sys.platform != "win32":
        return []
    psapi, kernel = ctypes.WinDLL("psapi"), ctypes.WinDLL("kernel32")
    pids = (ctypes.c_ulong * 4096)()
    size = ctypes.c_ulong()
    if not psapi.EnumProcesses(ctypes.byref(pids), ctypes.sizeof(pids), ctypes.byref(size)):
        return []
    found = []
    for pid in pids[: size.value // ctypes.sizeof(ctypes.c_ulong)]:
        handle = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            continue
        try:
            buffer = ctypes.create_unicode_buffer(1024)
            length = ctypes.c_ulong(len(buffer))
            if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                found.append((int(pid), buffer.value))
        finally:
            kernel.CloseHandle(handle)
    return found


def _kill(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                   creationflags=CREATE_NO_WINDOW, check=False)


def leftovers(runtime: Path, running: Iterable[tuple[int, str]], me: int) -> list[int]:
    """Pids started from ``runtime`` (any depth), except ``me``."""
    root = os.path.normcase(str(Path(runtime).resolve())) + os.sep
    return [pid for pid, path in running
            if pid != me and os.path.normcase(str(path)).startswith(root)]


def stop_leftovers(server_dir: Path, running: Callable[[], Iterable[tuple[int, str]]] = _running,
                   kill: Callable[[int], None] = _kill, executable: str | Path | None = None,
                   me: int | None = None) -> list[int]:
    """Closes this install's remaining processes; returns their pids."""
    runtime = installed_runtime(server_dir, executable)
    if runtime is None:
        return []
    pids = leftovers(runtime, running(), os.getpid() if me is None else me)
    for pid in pids:
        logger.info("Closing leftover IrisClick process %s", pid)
        kill(pid)
    return pids
