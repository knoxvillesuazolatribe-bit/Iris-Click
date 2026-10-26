r"""IrisClick entry point: starts the API server and opens the calibration page.

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
    calibration_url = f"{settings.site_url.rstrip('/')}/calibration"
    threading.Thread(
        target=lambda: (time.sleep(BROWSER_DELAY_S), webbrowser.open(calibration_url)),
        daemon=True,
    ).start()
    uvicorn.run("app.api.main:app", host=settings.host, port=settings.port, app_dir=str(SERVER_DIR))


if __name__ == "__main__":
    main()
