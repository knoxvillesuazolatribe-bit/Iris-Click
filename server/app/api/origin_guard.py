"""Desktop app: only IrisClick's own website may talk to this server from a browser.

The local server can open the webcam, start the tracking worker and move the
mouse, and it listens on 127.0.0.1 where any website the user visits could
try to reach it. Browsers apply CORS to page requests but NOT to WebSockets,
and a "simple" POST is sent even when CORS would hide the answer. So every
HTTP request and WebSocket handshake that carries a browser Origin must come
from an allowed site (CORS_ORIGINS: the local site and the hosted IrisClick
website). Requests without an Origin (the tracking worker, the launcher, tests)
are not from a web page and pass.
"""

import json
import logging

logger = logging.getLogger("irisclick.origin_guard")

FORBIDDEN = {"detail": "This website is not allowed to use IrisClick Desktop."}


class OriginGuard:
    def __init__(self, app, allowed: list[str]):
        self.app = app
        self.allowed = {o.rstrip("/").lower() for o in allowed if o and o != "*"}

    def _origin(self, scope) -> str | None:
        for key, value in scope.get("headers") or []:
            if key == b"origin":
                return value.decode("latin-1").rstrip("/").lower()
        return None

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        origin = self._origin(scope)
        if origin is None or origin in self.allowed:
            return await self.app(scope, receive, send)
        logger.warning("Blocked %s from origin %s to %s", scope["type"], origin, scope.get("path"))
        if scope["type"] == "websocket":
            # Refuse the handshake (the browser sees a failed connection, HTTP 403).
            await receive()  # websocket.connect
            await send({"type": "websocket.close", "code": 1008})
            return
        body = json.dumps(FORBIDDEN).encode()
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
