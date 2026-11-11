import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.user import User
from app.models.user_session import UserSession
from app.services.password_hashing import verify_password

from tests.auth.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, logs

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reset_admin_password.py"
NEW_PASSWORD = "a brand new passphrase"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("reset_admin_password_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admin(factory):
    with factory() as session:
        return session.scalars(select(User).where(User.email == ADMIN_EMAIL)).one()


def test_changes_the_password_and_logs_it(script, test_database, admin_id):
    message = script.reset_admin_password(test_database, " Admin@PDAO.ph ", NEW_PASSWORD)
    assert "Password changed for admin@pdao.ph" in message
    row = admin(test_database)
    assert verify_password(row.password_hash, NEW_PASSWORD)
    assert not verify_password(row.password_hash, ADMIN_PASSWORD)
    assert NEW_PASSWORD not in row.password_hash
    entries = logs(test_database, "password_changed")
    assert len(entries) == 1 and entries[0].user_id == admin_id
    assert NEW_PASSWORD not in entries[0].activity_description


def test_old_password_stops_working_and_sessions_end(script, test_database, signed_in_admin):
    assert signed_in_admin.get("/api/auth/me").status_code == 200
    message = script.reset_admin_password(test_database, ADMIN_EMAIL, NEW_PASSWORD)
    assert "1 open sign-in(s) ended" in message
    assert signed_in_admin.get("/api/auth/me").status_code == 401
    old = signed_in_admin.post("/api/auth/admin/login",
                               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert old.status_code == 401
    new = signed_in_admin.post("/api/auth/admin/login",
                               json={"email": ADMIN_EMAIL, "password": NEW_PASSWORD})
    assert new.status_code == 200


def test_only_this_admins_sessions_end(script, test_database, admin_id, make_user):
    other = make_user("Ana Cruz")
    later = datetime.now(timezone.utc) + timedelta(hours=1)
    with test_database() as session:
        session.add_all([
            UserSession(user_id=admin_id, token_hash="a" * 64, role="admin", expires_at=later),
            UserSession(user_id=other, token_hash="b" * 64, role="assistive_user",
                        expires_at=later)])
        session.commit()
    script.reset_admin_password(test_database, ADMIN_EMAIL, NEW_PASSWORD)
    with test_database() as session:
        open_ids = [s.user_id for s in session.scalars(
            select(UserSession).where(UserSession.revoked_at.is_(None)))]
    assert open_ids == [other]


@pytest.mark.parametrize("email, password", [
    ("not-an-email", NEW_PASSWORD),
    (ADMIN_EMAIL, "short"),
    ("nobody@pdao.ph", NEW_PASSWORD),
    (ADMIN_EMAIL, ADMIN_PASSWORD),
])
def test_bad_input_changes_nothing(script, test_database, admin_id, email, password):
    before = admin(test_database).password_hash
    with pytest.raises(ValueError):
        script.reset_admin_password(test_database, email, password)
    assert admin(test_database).password_hash == before
    assert logs(test_database, "password_changed") == []


def test_an_assistive_user_cannot_be_reset(script, test_database, make_user):
    make_user("Ana Cruz", email="ana@pdao.ph", password="her own passphrase")
    with pytest.raises(ValueError, match="No administrator"):
        script.reset_admin_password(test_database, "ana@pdao.ph", NEW_PASSWORD)


def test_password_must_be_typed_the_same_twice(script):
    answers = iter([NEW_PASSWORD, NEW_PASSWORD])
    assert script.ask_password(lambda _: next(answers)) == NEW_PASSWORD
    answers = iter([NEW_PASSWORD, "something else entirely"])
    with pytest.raises(ValueError, match="do not match"):
        script.ask_password(lambda _: next(answers))


def test_main_without_an_email_explains_usage(script, monkeypatch, capsys):
    monkeypatch.setattr(script, "AdminEmail", lambda: type("E", (), {"admin_email": ""})())
    assert script.main([]) == 2
    assert "Give the admin email" in capsys.readouterr().err
