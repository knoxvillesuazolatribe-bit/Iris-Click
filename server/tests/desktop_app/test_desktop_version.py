"""GET /api/desktop/version and the website's latest-version file stay in step."""

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import desktop_version
from app.version import VERSION

REPO = Path(__file__).resolve().parents[3]


def test_the_desktop_app_reports_its_version():
    app = FastAPI()
    app.include_router(desktop_version.router, prefix="/api")
    assert TestClient(app).get("/api/desktop/version").json() == {"app": "IrisClick Desktop", "version": VERSION}


def test_the_website_announces_this_version_and_a_real_download_link():
    latest = json.loads((REPO / "site" / "public" / "desktop-latest.json").read_text(encoding="utf-8"))
    assert latest["version"] == VERSION  # bump both together for a release
    assert latest["download_url"].startswith("https://") and latest["download_url"].endswith("IrisClick-Desktop-Setup.exe")


def test_the_pc_server_answers_the_version_check():
    from app.api import main
    response = TestClient(main.create_app()).get("/api/desktop/version")
    assert response.status_code == 200 and response.json()["version"] == VERSION
