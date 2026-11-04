r"""IrisClick entry point: starts the API server and opens the Login Selection page.

    cd server && .venv\Scripts\python main.py

The tracking worker is not started here: it starts only after the site's
calibration succeeds (see app/services/calibration_service.py).
"""

import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from app.config import get_settings

SERVER_DIR = Path(__file__).resolve().parent
BROWSER_DELAY_S = 1.5


def main():
    settings = get_settings()
    # Open Login Selection so admins and assistive users pick how to sign in.
    start_url = f"{settings.site_url.rstrip('/')}/"
    threading.Thread(
        target=lambda: (time.sleep(BROWSER_DELAY_S), webbrowser.open(start_url)),
        daemon=True,
    ).start()
    uvicorn.run("app.api.main:app", host=settings.host, port=settings.port, app_dir=str(SERVER_DIR))


if __name__ == "__main__":
    main()
