"""Window process: ``pythonw -m app.desktop_calibration --port 8000 --reason website``.

Started only by the local server (relay.spawn_window), never twice at once.
Its log is storage/desktop_calibration.log.
"""

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler

from app.config import STORAGE_DIR, get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IrisClick Desktop calibration window")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--reason", default="tray")
    args = parser.parse_args(argv)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(STORAGE_DIR / "desktop_calibration.log", maxBytes=500_000,
                                  backupCount=1, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from app.desktop_calibration.window import CalibrationWindow
    try:
        CalibrationWindow(args.port or get_settings().port, args.reason).run()
    except Exception:  # noqa: BLE001
        logging.getLogger("irisclick.desktop_calibration").exception("Calibration window failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
