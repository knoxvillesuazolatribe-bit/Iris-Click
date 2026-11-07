"""IrisClick Desktop: the program the IrisClick shortcut starts (no console window).

    runtime\\pythonw.exe server\\launch_irisclick.pyw            start IrisClick
    runtime\\pythonw.exe server\\launch_irisclick.pyw --stop     stop it

See app/launcher.py. Developers can keep using main.py.
"""

import os
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))
os.chdir(SERVER_DIR)

from app.launcher import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
