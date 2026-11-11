"""Which calibration screen the Calibrate / Recalibrate buttons open on this computer.

``IRISCLICK_CALIBRATION_SURFACE`` in IrisClick Desktop's ``server/.env``:

    web      (default) the website's calibration page, exactly as before
    desktop  the full-screen IrisClick Desktop calibration window

It is read on every call, so switching takes effect without a restart. A value
set in the process environment wins over the file (used by tests).
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values

from app.config import SERVER_DIR

ENV_NAME = "IRISCLICK_CALIBRATION_SURFACE"
WEB, DESKTOP = "web", "desktop"
Surface = Literal["web", "desktop"]


def surface(env_file: Path = SERVER_DIR / ".env") -> Surface:
    value = os.environ.get(ENV_NAME)
    if value is None:
        try:
            value = dotenv_values(env_file).get(ENV_NAME)
        except OSError:
            value = None
    value = (value or "").strip().lower()
    return DESKTOP if value == DESKTOP else WEB
