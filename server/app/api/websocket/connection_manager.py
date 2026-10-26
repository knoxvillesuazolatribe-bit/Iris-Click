import asyncio

from fastapi import WebSocket
from pydantic import BaseModel


class ConnectionManager:
    """Single-holder WebSocket registry with serialised sends.

    Only one calibration may run at a time because it owns the webcam. Sends
    are locked per socket: the status stream and point results come from
    different tasks, and Starlette does not allow concurrent sends.
    """

    def __init__(self):
        self._active: WebSocket | None = None
        self._send_locks: dict[WebSocket, asyncio.Lock] = {}

    async def acquire(self, websocket: WebSocket, timeout: float = 5.0) -> bool:
        # A page reload connects before the old socket's cleanup has released
        # the camera, so wait for it briefly instead of refusing at once.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while self._active is not None:
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(0.05)
        self._active = websocket
        self._send_locks[websocket] = asyncio.Lock()
        return True

    def release(self, websocket: WebSocket):
        if self._active is websocket:
            self._active = None
        self._send_locks.pop(websocket, None)

    async def send(self, websocket: WebSocket, message: BaseModel):
        lock = self._send_locks.setdefault(websocket, asyncio.Lock())
        async with lock:
            await websocket.send_text(message.model_dump_json())

