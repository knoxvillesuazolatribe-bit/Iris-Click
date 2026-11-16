"""Control bar "Home": show the website's Home in the browser (one home, on the web).

The open IrisClick pages are asked to go Home through the local server (POST
/api/desktop/go-home). Only when no IrisClick page is open, or the server does not answer, the
website's Home is opened in a normal Edge browser window: the hosted site, never a
developer address and never an app-style window that looks like a second home.
"""

import json
import logging
import urllib.request
from collections.abc import Callable

logger = logging.getLogger("irisclick.web_home")

TIMEOUT_S = 3.0


def _post(url: str) -> dict:
    request = urllib.request.Request(url, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 - 127.0.0.1 only
        return json.loads(response.read().decode("utf-8") or "{}")


def _open_home_window() -> None:
    from app import launcher
    launcher.open_window(launcher.website_url().rstrip("/") + "/home", launcher.find_edge())


def go_home(port: int, post: Callable[[str], dict] = _post,
            open_window: Callable[[], None] = _open_home_window) -> str:
    """"pages" when open IrisClick pages were asked, "window" when a browser window was opened."""
    try:
        if int(post(f"http://127.0.0.1:{port}/api/desktop/go-home").get("pages", 0)) > 0:
            return "pages"
    except Exception:  # noqa: BLE001 - fall back to opening the window
        logger.info("No answer from the local server; opening the website's Home")
    try:
        open_window()
    except Exception:  # noqa: BLE001 - a Home button must never stop eye tracking
        logger.warning("Could not open Home", exc_info=True)
    return "window"
