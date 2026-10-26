r"""Voice guidance check: speaks one line. Run from server\ with the venv Python.

    .venv\Scripts\python scripts\check_voice.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.desktop.voice import Speaker  # noqa: E402

SPEAK_TIMEOUT_S = 8.0


def main() -> int:
    speaker = Speaker()
    speaker.start()
    speaker.say("IrisClick voice check. Please move forward a little.")
    speaker.stop()
    speaker._thread.join(timeout=SPEAK_TIMEOUT_S)
    print(f"voice: {'ok' if speaker.available else 'UNAVAILABLE (see log)'}")
    return 0 if speaker.available else 1


if __name__ == "__main__":
    sys.exit(main())
