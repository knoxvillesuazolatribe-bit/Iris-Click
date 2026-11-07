"""Database option 2: IrisClick Desktop syncs a local database through the hosted API.

Two databases: the test database stands in for Supabase (the hosted side); a second
SQLite file is the PC's local copy. HTTP calls go to the hosted routes in-process.
"""

import time
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.routes import desktop_link
from app.cloud import desktop_api
from app.models import database
from app.models.accessibility_settings import AccessibilitySettings
from app.models.base import Base
from app.models.calibration_record import CalibrationRecord
from app.models.system_log import SystemLog
from app.models.system_settings import SystemSettings
from app.services import accessibility_service, desktop_tokens
from app.desktop_sync import sync

from tests.auth.conftest import make_user  # noqa: F401  (fixture)

WHEN = datetime(2026, 11, 7, 8, 55, tzinfo=UTC)


@pytest.fixture
def hosted(monkeypatch):
    monkeypatch.setenv(desktop_tokens.SECRET_ENV, "s" * 40)
    app = FastAPI()
    app.include_router(desktop_api.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def local(tmp_path, monkeypatch, hosted):
    """The PC: its own SQLite file, desktop mode on, HTTP routed to the hosted app."""
    engine = database.enable_sqlite_foreign_keys(
        create_engine(f"sqlite:///{(tmp_path / 'local.db').as_posix()}", connect_args={"check_same_thread": False}))
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(sync, "database", SimpleNamespace(get_engine=lambda: engine, get_session_factory=lambda: factory))
    monkeypatch.setattr(sync, "state_path", tmp_path / "sync_state.json")
    monkeypatch.setattr(sync, "desktop_mode", lambda: True)
    monkeypatch.setattr(desktop_link, "session_path", tmp_path / "desktop_session.json")

    def http(method, path, token, body=None):
        response = hosted.request(method, path, headers={"Authorization": f"Bearer {token}"}, json=body)
        return response.status_code, response.json()

    monkeypatch.setattr(sync, "http", http)
    sync.prepare_local_db()
    return factory


def link(user_id, name="Ana Cruz"):
    token, expires = desktop_tokens.make(desktop_tokens.DESKTOP, user_id)
    desktop_link._save_session({"desktop_token": token, "expires_at": expires,
                                "user": {"user_id": user_id, "full_name": name}})
    return token


def test_pull_brings_the_user_their_settings_and_the_global_defaults(local, make_user, test_database):
    ana = make_user("Ana Cruz")
    with test_database() as db:  # the hosted database
        db.add(AccessibilitySettings(user_id=ana, dwell_enabled=True, dwell_ms=900, cursor_smoothing=0.45,
                                     blink_to_click=False, blink_sensitivity=0.2, voice_volume=60,
                                     edge_scroll_enabled=False))
        db.add(SystemSettings(setting_id=1, app_name="IrisClick PDAO", dwell_ms=800))
        db.commit()
    link(ana)
    assert sync.sync_once()["status"] == "ok"
    with local() as db:  # the PC's copy: exactly what the worker reads
        overrides = accessibility_service.worker_overrides(db, ana)
    assert overrides["dwell_click_enabled"] is True and overrides["dwell_ms"] == 900
    assert overrides["blink_click_enabled"] is False and overrides["edge_scroll_enabled"] is False


def test_calibrations_and_logs_made_on_the_pc_reach_the_hosted_database_once(local, make_user, test_database):
    ana = make_user("Ana Cruz")
    ben = make_user("Ben Reyes")
    link(ana)
    sync.sync_once()  # pulls Ana into the local copy
    with local() as db:  # what calibration_records / screenshot_capture write on the PC
        db.merge(sync.User(user_id=ben, full_name="Ben Reyes", role="assistive_user", status="active"))
        db.flush()
        db.add(CalibrationRecord(user_id=ana, profile_file_id="20261107T085500", profile_name="Desk",
                                 status="Successful", accuracy_score=Decimal("95.50"), error_fraction=0.045,
                                 feature_source="eyeball_v1", camera_index=0, sample_count=300,
                                 calibration_data={"model": {"k": 1}}, calibration_date=WHEN))
        db.add(CalibrationRecord(user_id=ana, profile_name="Desk", status="Failed",
                                 failure_reason="Not enough clear eye images at a calibration dot.",
                                 calibration_date=WHEN))
        db.add(CalibrationRecord(user_id=ben, profile_name="Other", status="Failed", calibration_date=WHEN))
        db.add(SystemLog(user_id=ana, activity_type="calibration", activity_description="saved", log_date=WHEN))
        db.add(SystemLog(user_id=ana, activity_type="screenshot", activity_description="Screenshot saved: a.png",
                         log_date=WHEN))
        db.add(SystemLog(user_id=ana, activity_type="login", activity_description="not synced", log_date=WHEN))
        db.commit()

    result = sync.sync_once()
    assert result == {"status": "ok", "calibrations": 2, "logs": 2}
    assert sync.sync_once() == {"status": "ok", "calibrations": 0, "logs": 0}  # nothing twice
    with test_database() as db:
        rows = db.scalars(select(CalibrationRecord).order_by(CalibrationRecord.calibration_id)).all()
        assert [(r.user_id, r.status) for r in rows] == [(ana, "Successful"), (ana, "Failed")]
        assert rows[0].accuracy_score == Decimal("95.50") and rows[0].calibration_data == {"model": {"k": 1}}
        logs = db.scalars(select(SystemLog).where(SystemLog.user_id == ana)).all()
        assert sorted(l.activity_type for l in logs) == ["calibration", "screenshot"]


def test_a_lost_answer_does_not_duplicate_rows(hosted, make_user, test_database, monkeypatch):
    monkeypatch.setenv(desktop_tokens.SECRET_ENV, "s" * 40)
    ana = make_user("Ana Cruz")
    token, _ = desktop_tokens.make(desktop_tokens.DESKTOP, ana)
    body = {"records": [{"profile_name": "Desk", "status": "Failed", "calibration_date": WHEN.isoformat()}]}
    headers = {"Authorization": f"Bearer {token}"}
    assert hosted.post("/api/desktop/calibrations", json=body, headers=headers).json()["saved"] == 1
    assert hosted.post("/api/desktop/calibrations", json=body, headers=headers).json()["saved"] == 0


def test_the_hosted_api_only_accepts_a_valid_desktop_token_and_known_rows(hosted, make_user, monkeypatch):
    ana = make_user("Ana Cruz")
    assert hosted.get("/api/desktop/profile").status_code == 401
    link_token, _ = desktop_tokens.make(desktop_tokens.LINK, ana)  # wrong kind of token
    assert hosted.get("/api/desktop/profile", headers={"Authorization": f"Bearer {link_token}"}).status_code == 401
    token, _ = desktop_tokens.make(desktop_tokens.DESKTOP, ana)
    headers = {"Authorization": f"Bearer {token}"}
    assert hosted.get("/api/desktop/profile", headers=headers).json()["user"]["full_name"] == "Ana Cruz"
    bad = {"logs": [{"activity_type": "user_created", "log_date": WHEN.isoformat()}]}
    assert hosted.post("/api/desktop/logs", json=bad, headers=headers).status_code == 422
    too_many = {"logs": [{"activity_type": "screenshot", "log_date": WHEN.isoformat()}] * 51}
    assert hosted.post("/api/desktop/logs", json=too_many, headers=headers).status_code == 422


def test_rows_are_saved_for_the_token_user_whatever_the_request_says(hosted, make_user, test_database):
    ana = make_user("Ana Cruz")
    make_user("Ben Reyes")
    token, _ = desktop_tokens.make(desktop_tokens.DESKTOP, ana)
    body = {"records": [{"profile_name": "x", "status": "Failed", "calibration_date": WHEN.isoformat(),
                         "user_id": 999}]}
    hosted.post("/api/desktop/calibrations", json=body, headers={"Authorization": f"Bearer {token}"})
    with test_database() as db:
        assert db.scalars(select(CalibrationRecord.user_id)).all() == [ana]


def test_sync_status_off_unlinked_expired_and_offline(local, monkeypatch, make_user):
    monkeypatch.setattr(sync, "desktop_mode", lambda: False)
    assert sync.sync_once() == {"status": "off"}
    monkeypatch.setattr(sync, "desktop_mode", lambda: True)
    assert sync.sync_once() == {"status": "not_linked"}
    link(make_user("Ana Cruz"))
    monkeypatch.setattr(sync, "http", lambda *a, **k: (401, {"detail": "expired"}))
    assert sync.sync_once() == {"status": "link_expired"}

    def offline(*a, **k):
        raise OSError("no internet")

    monkeypatch.setattr(sync, "http", offline)
    assert sync.sync_once() == {"status": "offline"}


def test_local_copy_is_refreshed_after_an_update_changes_the_tables(local, monkeypatch):
    sync._save_state({"schema": "older-version", "calibration_id": 5})
    sync.prepare_local_db()
    state = sync._load_state()
    assert state["schema"] == sync.schema_fingerprint() and "calibration_id" not in state
    with local() as db:
        assert db.scalars(select(CalibrationRecord)).all() == []


def test_desktop_mode_needs_a_website_address_and_no_database_host(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(desktop_link, "cloud_url", lambda: "https://iris.example")
    local_db = get_settings().model_copy(update={"db_host": ""})
    monkeypatch.setattr(sync, "get_settings", lambda: local_db)
    assert sync.desktop_mode() is True
    monkeypatch.setattr(sync, "get_settings", lambda: local_db.model_copy(update={"db_host": "pooler"}))
    assert sync.desktop_mode() is False  # today's PC with Supabase: sync never runs
    monkeypatch.setattr(desktop_link, "cloud_url", lambda: "")
    monkeypatch.setattr(sync, "get_settings", lambda: local_db)
    assert sync.desktop_mode() is False


def test_the_loop_stops_when_asked(monkeypatch):
    import threading
    calls = []
    monkeypatch.setattr(sync, "sync_once", lambda: calls.append(1) or {"status": "off"})
    monkeypatch.setattr(desktop_link, "load_session", lambda: None)
    stop = threading.Event()
    worker = threading.Thread(target=sync.run_forever, args=(stop, 0.05, 0.05))
    worker.start()
    time.sleep(0.2)
    stop.set()
    worker.join(2)
    assert not worker.is_alive() and len(calls) >= 2


def test_through_the_real_online_server_only_the_four_desktop_paths_skip_the_access_code(monkeypatch, make_user):
    from app.cloud import access
    from app.cloud import main as cloud
    monkeypatch.setenv(desktop_tokens.SECRET_ENV, "s" * 40)
    monkeypatch.setenv(access.CODE_ENV, "test-access-code")
    ana = make_user("Ana Cruz")
    token, _ = desktop_tokens.make(desktop_tokens.DESKTOP, ana)
    with TestClient(cloud.create_app()) as c:
        headers = {"Authorization": f"Bearer {token}"}
        assert c.get("/api/desktop/profile", headers=headers).json()["user"]["user_id"] == ana
        assert c.post("/api/desktop/logs", json={"logs": []}, headers=headers).json() == {"received": 0, "saved": 0}
        assert c.get("/api/desktop/profile").status_code == 401  # no token: refused by the route itself
        assert c.get("/api/desktop/other").json()["code"] == "access_required"
        assert c.get("/api/assistive/users").json()["code"] == "access_required"
