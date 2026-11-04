from sqlalchemy import select

from app.models import database
from app.models.system_log import SystemLog
from app.services.system_log_service import DESCRIPTION_MAX_CHARS, log_activity


def _logs(factory):
    with factory() as session:
        return session.scalars(select(SystemLog)).all()


def test_log_activity_writes_a_row(test_database):
    assert log_activity("login", "Admin signed in") is True
    [row] = _logs(test_database)
    assert (row.activity_type, row.activity_description, row.user_id) == (
        "login", "Admin signed in", None)
    assert row.log_date is not None


def test_long_descriptions_are_trimmed(test_database):
    log_activity("message", "x" * (DESCRIPTION_MAX_CHARS + 50))
    [row] = _logs(test_database)
    assert len(row.activity_description) == DESCRIPTION_MAX_CHARS


def test_a_broken_database_returns_false_instead_of_raising(monkeypatch, caplog):
    def broken():
        raise RuntimeError("database down")

    monkeypatch.setattr(database, "get_session_factory", broken)
    assert log_activity("login") is False
    assert "database down" in caplog.text


def test_with_a_session_the_row_joins_the_callers_transaction(test_database):
    with test_database() as session:
        assert log_activity("sos", "SOS sent", session=session) is True
        session.rollback()
    assert _logs(test_database) == []
