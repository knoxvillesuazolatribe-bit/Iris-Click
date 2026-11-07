"""Vercel entry point for the IrisClick online copy (see server/app/cloud/ and docs/vercel-backup.md).

Vercel runs this file as one Python function; vercel.json sends every /api/... request here.
The PC keeps using server/main.py.
"""

import os
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

from app.cloud.main import VercelPaths, configure_runtime, create_app  # noqa: E402

# Vercel only allows writing under /tmp.
configure_runtime(Path(os.environ.get("IRISCLICK_STORAGE_DIR", "/tmp/irisclick")))

app = VercelPaths(create_app())
