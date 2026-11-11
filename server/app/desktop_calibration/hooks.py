"""What the launcher and the tracking worker call (each a one-line hook).

They run in their own processes, so they ask the local server to open the window;
the server is the only one that starts it. Every helper swallows its own errors:
a failure here must never stop the launcher or the tracking worker.
"""

import json
import logging
import urllib.request

from app.desktop_calibration import surface as _surface

logger = logging.getLogger("irisclick.desktop_calibration.hooks")

TIMEOUT_S = 5.0


def surface() -> str:
    try:
        return _surface.surface()
    except Exception:  # noqa: BLE001 - anything odd means today's behaviour
        return _surface.WEB


def _port(port: int | None) -> int:
    if port:
        return port
    from app.config import get_settings
    return get_settings().port


def open_window(reason: str = "tray", first_run: bool = False, port: int | None = None,
                opener=urllib.request.urlopen) -> bool:
    """Asks the local server to open the calibration window; True if it opened."""
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{_port(port)}/api/desktop/calibration/open",
            data=json.dumps({"reason": reason, "first_run": first_run}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with opener(request, timeout=TIMEOUT_S) as response:
            return bool(json.loads(response.read().decode("utf-8")).get("opened"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Desktop calibration window not opened: %s", exc)
        return False


def first_run_calibration(port: int) -> bool:
    """Launcher: no calibration on this computer yet. Opens the window only in desktop
    mode with someone linked (the server checks both); otherwise nothing happens."""
    if surface() != _surface.DESKTOP:
        return False
    return open_window("first_run", first_run=True, port=port)
