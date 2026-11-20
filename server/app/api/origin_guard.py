"""Desktop app: only IrisClick's own website may talk to this server from a browser.

The local server can open the webcam, start the tracking worker and move the
mouse, and it listens on 127.0.0.1 where any website the user visits could
try to reach it. Browsers apply CORS to page requests but NOT to WebSockets,
and a "simple" POST is sent even when CORS would hide the answer. So every
HTTP request and WebSocket handshake that carries a browser Origin must come
from an allowed site (CORS_ORIGINS: the local site and the hosted IrisClick
website). Requests without an Origin (the tracking worker, the launcher, tests)
are not from a web page and pass.

Security audit (DNS rebinding): a website can point its own name at 127.0.0.1; the
browser then treats this server as that site and sends plain GETs with no Origin at all.
So every request must also be addressed to this computer by its Host header
(127.0.0.1 / localhost / [::1]); a rebinding site's name never passes. "testserver" is
the test client's single-label name, which no public DNS can point here.
"""

import json
import logging

logger = logging.getLogger("irisclick.origin_guard")

FORBIDDEN = {"detail": "This website is not allowed to use IrisClick Desktop."}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}


def host_name(value: str) -> str:
    """"127.0.0.1:8000" -> "127.0.0.1"; "[::1]:8000" -> "::1"."""
    value = value.strip().lower()
    if value.startswith("["):
        return value[1:value.find("]")] if "]" in value else value
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


class OriginGuard:
    def __init__(self, app, allowed: list[str]):
        self.app = app
        self.allowed = {o.rstrip("/").lower() for o in allowed if o and o != "*"}

    def _origin(self, scope) -> str | None:
        return self._header(scope, b"origin", lambda v: v.rstrip("/").lower())

    @staticmethod
    def _header(scope, name: bytes, clean):
        for key, value in scope.get("headers") or []:
            if key == name:
                return clean(value.decode("latin-1"))
        return None

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        origin = self._origin(scope)
        host = self._header(scope, b"host", host_name)
        local = host is None or host in LOCAL_HOSTS
        if local and (origin is None or origin in self.allowed):
            return await self.app(scope, receive, send)
        logger.warning("Blocked %s from origin %s, host %s to %s", scope["type"], origin, host, scope.get("path"))
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
