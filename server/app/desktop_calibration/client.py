"""The calibration window's two connections to IrisClick Desktop's local server.

    /api/ws/calibration                  the existing calibration socket (engine)
    /api/ws/desktop-calibration/agent    reports progress to the website, receives cancel

Both use the ``websockets`` sync client (already installed with uvicorn[standard]).
A reader thread puts every received message on a queue the Tk loop drains, and
``None`` on the queue means the connection closed. No Origin header is sent: the
local server only lets browsers in from allowed websites, and this is not a browser.
"""

import json
import logging
import queue
import threading

logger = logging.getLogger("irisclick.desktop_calibration.client")

OPEN_TIMEOUT_S = 10.0


class Channel:
    def __init__(self, url: str, connect=None):
        self.url = url
        self.inbox: queue.Queue[dict | None] = queue.Queue()
        self._connect = connect
        self._ws = None
        self._lock = threading.Lock()
        self.closed = False

    def open(self) -> None:
        connect = self._connect
        if connect is None:
            from websockets.sync.client import connect
        self._ws = connect(self.url, open_timeout=OPEN_TIMEOUT_S, max_size=2 ** 22)
        threading.Thread(target=self._read, name=f"ws-{self.url.rsplit('/', 1)[-1]}", daemon=True).start()

    def _read(self) -> None:
        try:
            for raw in self._ws:
                try:
                    self.inbox.put(json.loads(raw))
                except ValueError:
                    continue
        except Exception as exc:  # noqa: BLE001 - any close ends the channel
            logger.info("Channel %s closed: %s", self.url, exc)
        finally:
            self.closed = True
            self.inbox.put(None)

    def send(self, message: dict) -> None:
        if self._ws is None or self.closed:
            return
        try:
            with self._lock:
                self._ws.send(json.dumps(message))
        except Exception as exc:  # noqa: BLE001
            logger.info("Send on %s failed: %s", self.url, exc)

    def drain(self) -> list[dict | None]:
        items = []
        while True:
            try:
                items.append(self.inbox.get_nowait())
            except queue.Empty:
                return items

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:  # noqa: BLE001
                pass


def urls(port: int) -> tuple[str, str]:
    base = f"ws://127.0.0.1:{port}/api"
    return f"{base}/ws/calibration", f"{base}/ws/desktop-calibration/agent"
