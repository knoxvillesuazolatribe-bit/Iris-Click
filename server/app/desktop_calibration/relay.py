"""The current desktop calibration run, kept by IrisClick Desktop's local server.

The server is the only one that starts the calibration window (website, launcher
and tracking worker all ask it), so there is never more than one window. The
window connects back on the agent channel and reports its progress; the relay
keeps the latest state and passes every event on to the open website pages, so
a page that reconnects (refresh, Desktop restart) catches up at once.

If the window closes without a successful calibration, eye tracking is started
again with the newest calibration, so a person is not left without a cursor.
"""

import asyncio
import contextlib
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from fastapi import WebSocket

from app.config import SERVER_DIR
from app.desktop_calibration.messages import event

logger = logging.getLogger("irisclick.desktop_calibration")

IDLE, STARTING, RUNNING, FINISHED = "idle", "starting", "running", "finished"
# A window that has not connected by then is reported as not opened.
CONNECT_TIMEOUT_S = 25.0
DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000


def spawn_window(port: int, reason: str) -> int:
    """Starts ``python -m app.desktop_calibration`` without a console; returns its pid."""
    executable = Path(sys.executable)
    windowless = executable.with_name("pythonw.exe")
    process = subprocess.Popen(
        [str(windowless if windowless.is_file() else executable),
         "-m", "app.desktop_calibration", "--port", str(port), "--reason", reason],
        cwd=SERVER_DIR,
        creationflags=(DETACHED_PROCESS | CREATE_NO_WINDOW) if sys.platform == "win32" else 0,
        close_fds=True,
    )
    logger.info("Desktop calibration window started (pid=%s, reason=%s)", process.pid, reason)
    return process.pid


def _pid_alive(pid: int) -> bool:
    from app.services.tracking_service import pid_alive
    return pid_alive(pid)


def _restart_tracking() -> None:
    from app.services.tracking_service import get_tracking_service
    try:
        get_tracking_service().start()
    except LookupError:
        logger.info("No calibration to restart eye tracking with")
    except Exception:  # noqa: BLE001
        logger.exception("Eye tracking could not restart after desktop calibration")


class Relay:
    def __init__(self, spawn: Callable[[int, str], int] = spawn_window,
                 alive: Callable[[int], bool] = _pid_alive,
                 restart_tracking: Callable[[], None] = _restart_tracking,
                 connect_timeout_s: float = CONNECT_TIMEOUT_S):
        self._spawn = spawn
        self._alive = alive
        self._restart_tracking = restart_tracking
        self._connect_timeout_s = connect_timeout_s
        self.status = IDLE
        self.done = 0
        self.total = 13
        self.advice: dict | None = None
        self.last_result: dict | None = None
        self.pid: int | None = None
        self.agent: WebSocket | None = None
        self.sites: set[WebSocket] = set()
        # Starlette refuses two sends at once on one socket (events + tracking pushes).
        self._locks: dict[WebSocket, asyncio.Lock] = {}
        self._cancel_pending = False
        self._succeeded = False
        self._ended = False
        self._timeout_task: asyncio.Task | None = None

    # ---- state
    def snapshot(self) -> dict:
        return event("calibration.state", status=self.status, done=self.done, total=self.total,
                     advice=self.advice, last_result=self.last_result)

    def window_open(self) -> bool:
        return self.agent is not None or (self.pid is not None and self._alive(self.pid))

    def add_site(self, ws: WebSocket) -> None:
        self.sites.add(ws)
        self._locks[ws] = asyncio.Lock()

    def remove_site(self, ws: WebSocket) -> None:
        self.sites.discard(ws)
        self._locks.pop(ws, None)

    async def send(self, ws: WebSocket, message: dict) -> None:
        lock = self._locks.setdefault(ws, asyncio.Lock())
        async with lock:
            await ws.send_json(message)

    async def broadcast(self, message: dict) -> None:
        for ws in list(self.sites):
            try:
                await self.send(ws, message)
            except Exception:  # noqa: BLE001 - a closed page is simply dropped
                self.remove_site(ws)

    # ---- opening the window
    async def open(self, port: int, reason: str) -> dict[str, Any]:
        if self.window_open():
            return {"opened": False, "reason": "already_open"}
        try:
            self.pid = await asyncio.to_thread(self._spawn, port, reason)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Desktop calibration window could not start")
            await self.broadcast(event("calibration.error", message="The calibration window could not open."))
            return {"opened": False, "reason": "spawn_failed", "detail": str(exc)}
        self.status, self.done, self.advice = STARTING, 0, None
        self.last_result, self._succeeded, self._cancel_pending, self._ended = None, False, False, False
        self._timeout_task = asyncio.create_task(self._watch_connect())
        await self.broadcast(self.snapshot())
        return {"opened": True}

    async def _watch_connect(self) -> None:
        await asyncio.sleep(self._connect_timeout_s)
        if self.status == STARTING and self.agent is None:
            logger.warning("Desktop calibration window did not connect")
            self.status, self.pid = IDLE, None
            await self.broadcast(event("calibration.error",
                                       message="The calibration window did not open. Try again."))
            await self.broadcast(self.snapshot())

    # ---- the window's channel
    async def agent_connected(self, ws: WebSocket) -> bool:
        if self.agent is not None:
            return False
        self.agent = ws
        if self._timeout_task is not None:
            self._timeout_task.cancel()
            self._timeout_task = None
        if self.status == IDLE:  # opened directly (e.g. a developer running the module)
            self.status, self._succeeded = STARTING, False
        if self._cancel_pending:
            self._cancel_pending = False
            await self._send_agent(event("calibration.cancel"))
        return True

    async def agent_event(self, message: dict) -> None:
        kind = message["type"]
        if kind == "calibration.started":
            self.status, self.done, self.total = RUNNING, 0, message["total"]
            self.advice, self.last_result, self._ended = None, None, False
        elif kind == "calibration.progress":
            self.done, self.total = message["done"], message["total"]
        elif kind == "calibration.advice":
            self.advice = {"kind": message["kind"], "text": message.get("text")} if message["kind"] else None
        elif kind == "calibration.result":
            self.last_result = {k: message.get(k) for k in ("status", "accuracy_percent", "low_accuracy", "message")}
            self.advice = None
            if message["status"] == "success":
                self._succeeded = True
                self.done = self.total
            self.status, self._ended = FINISHED, True  # the window may still try again on its own
        elif kind == "calibration.cancelled":
            self.status, self.advice, self._ended = FINISHED, None, True
        await self.broadcast(message)

    async def agent_disconnected(self, ws: WebSocket) -> None:
        if ws is not self.agent:
            return
        self._locks.pop(ws, None)
        self.agent, self.pid = None, None
        was_active = self.status in (STARTING, RUNNING)
        self.status, self.advice = IDLE, None
        if was_active and not self._ended:
            await self.broadcast(event("calibration.cancelled", reason="desktop_closed"))
        await self.broadcast(self.snapshot())
        if not self._succeeded:
            await asyncio.to_thread(self._restart_tracking)

    async def _send_agent(self, message: dict) -> None:
        if self.agent is None:
            return
        with contextlib.suppress(Exception):
            await self.send(self.agent, message)

    # ---- the website's requests
    async def cancel(self) -> None:
        if self.agent is not None:
            await self._send_agent(event("calibration.cancel"))
        elif self.status == STARTING:
            self._cancel_pending = True
            await self.broadcast(event("calibration.cancelled", reason="cancelled"))


relay = Relay()
