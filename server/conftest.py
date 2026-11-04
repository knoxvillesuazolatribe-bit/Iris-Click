"""Test-wide database isolation.

Calibration now also writes to the database (app/services/calibration_records.py).
Without this, the existing calibration tests would send rows to the real
Supabase database from server/.env. Every test instead gets an empty SQLite
file with all tables, and nothing reaches the network.
"""

import shutil

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models.all_models  # noqa: F401  (registers every table on Base.metadata)
from app.models import database
from app.models.base import Base
from app.services import active_user
from app.services.background_db import writer

WRITER_IDLE_TIMEOUT_S = 10.0


def sqlite_engine(path):
    return database.enable_sqlite_foreign_keys(
        create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False}))


@pytest.fixture(scope="session")
def empty_database_file(tmp_path_factory):
    """An SQLite file with every table, built once and copied for each test."""
    path = tmp_path_factory.mktemp("db-template") / "irisclick-empty.db"
    engine = sqlite_engine(path)
    Base.metadata.create_all(engine)
    engine.dispose()
    return path


@pytest.fixture(autouse=True)
def test_database(empty_database_file, tmp_path_factory, monkeypatch):
    """Session factory for this test's own SQLite database (all tables created)."""
    path = tmp_path_factory.mktemp("db") / "irisclick-test.db"
    shutil.copyfile(empty_database_file, path)
    engine = sqlite_engine(path)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "get_engine", lambda: engine)
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    active_user.set_user_id(None)
    yield factory
    # Finish queued background writes while they still point at this file.
    writer.wait_idle(WRITER_IDLE_TIMEOUT_S)
    active_user.set_user_id(None)
    engine.dispose()
