r"""Target-assist check: lists clickable controls UI Automation sees in the
foreground window (read-only; nothing is moved or clicked). Run from server\:

    .venv\Scripts\python scripts\check_targets.py [seconds_to_switch_window]

Use the delay to bring e.g. a browser to the front before the scan.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.desktop.display import enable_dpi_awareness  # noqa: E402
from app.desktop.target_assist import REFRESH_SECONDS, TargetFinder  # noqa: E402


def main() -> int:
    delay = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    enable_dpi_awareness()
    time.sleep(delay)
    finder = TargetFinder()
    finder.start()
    time.sleep(REFRESH_SECONDS * 3)
    finder.stop()
    targets = finder.targets()
    print(f"ui automation: {'ok' if finder.available else 'UNAVAILABLE'}, {len(targets)} targets")
    for target in sorted(targets, key=lambda t: (t.top, t.left))[:15]:
        print(f"  {target.name[:40]!r:44} ({target.left},{target.top})-({target.right},{target.bottom})")
    return 0 if finder.available else 1


if __name__ == "__main__":
    sys.exit(main())
