import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.user import User
from app.services.password_hashing import verify_password

from tests.auth.conftest import logs

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "create_admin.py"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("create_admin_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_creates_an_admin_with_a_hashed_password(script, test_database):
    message = script.create_admin(test_database, " Admin@PDAO.ph ", "a long passphrase",
                                  "PDAO Admin")
    assert "created" in message and "delete ADMIN_PASSWORD" in message
    with test_database() as session:
        admin = session.scalars(select(User)).one()
    assert (admin.email, admin.role, admin.status) == ("admin@pdao.ph", "admin", "active")
    assert verify_password(admin.password_hash, "a long passphrase")
    assert len(logs(test_database, "user_created")) == 1


def test_running_twice_changes_nothing(script, test_database):
    script.create_admin(test_database, "admin@pdao.ph", "a long passphrase", "PDAO Admin")
    message = script.create_admin(test_database, "admin@pdao.ph", "another passphrase", "X")
    assert "already exists" in message
    with test_database() as session:
        admin = session.scalars(select(User)).one()
    assert verify_password(admin.password_hash, "a long passphrase")


@pytest.mark.parametrize("email, password, name", [
    ("not-an-email", "a long passphrase", "Admin"),
    ("admin@pdao.ph", "short", "Admin"),
    ("admin@pdao.ph", "a long passphrase", "   "),
])
def test_bad_settings_are_refused(script, test_database, email, password, name):
    with pytest.raises(ValueError):
        script.create_admin(test_database, email, password, name)
