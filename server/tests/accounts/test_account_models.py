from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.accounts import mode
from app.models.account_models import Device, DeviceAccount, PinAttempt, SetupCode, UserAccount
from app.models.timestamps import utc_now
from app.models.user import User


def add_user(factory, name="Mari", role="assistive_user"):
    admin = role == "admin"  # admins must have an email and a password (ck_users_admin_login)
    with factory() as session:
        user = User(full_name=name, role=role, email="admin@pdao.ph" if admin else None,
                    password_hash="$argon2id$fake" if admin else None)
        session.add(user)
        session.commit()
        return user.user_id


def test_an_account_with_a_device_and_a_setup_code(test_database):
    uid = add_user(test_database)
    admin = add_user(test_database, "PDAO Admin", "admin")
    with test_database() as s:
        s.add(UserAccount(user_id=uid, username="mari_lapu", username_key="mari_lapu",
                          mobile_number="+639178082488", pin_hash="$argon2id$fake"))
        device = Device(device_key_hash="a" * 64)
        s.add(device)
        s.flush()
        s.add(DeviceAccount(device_id=device.device_id, user_id=uid, remembered=True))
        s.add(PinAttempt(device_id=device.device_id, user_id=uid, kind="pin"))
        s.add(SetupCode(user_id=uid, code_hash="$argon2id$fake", expires_at=utc_now() + timedelta(hours=24),
                        created_by=admin))
        s.commit()
    with test_database() as s:
        account = s.get(UserAccount, uid)
        assert (account.signup_source, account.must_reset_pin) == ("self", False)
        assert s.scalars(select(Device)).one().is_shared is False
        assert s.scalars(select(DeviceAccount)).one().remembered is True


def test_usernames_are_unique_ignoring_case(test_database):
    a, b = add_user(test_database, "Mari"), add_user(test_database, "Mia")
    with test_database() as s:
        s.add(UserAccount(user_id=a, username="Mari", username_key="mari"))
        s.commit()
        s.add(UserAccount(user_id=b, username="MARI", username_key="mari"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_a_computer_is_stored_once_and_an_account_once_per_computer(test_database):
    uid = add_user(test_database)
    with test_database() as s:
        d = Device(device_key_hash="b" * 64)
        s.add(d)
        s.flush()
        s.add(DeviceAccount(device_id=d.device_id, user_id=uid))
        s.commit()
        s.add(DeviceAccount(device_id=d.device_id, user_id=uid))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
        s.add(Device(device_key_hash="b" * 64))
        with pytest.raises(IntegrityError):
            s.commit()


def test_deleting_a_user_removes_their_account_rows(test_database):
    uid = add_user(test_database)
    with test_database() as s:
        d = Device(device_key_hash="c" * 64)
        s.add_all([d, UserAccount(user_id=uid, username="mia", username_key="mia")])
        s.flush()
        s.add(DeviceAccount(device_id=d.device_id, user_id=uid))
        s.commit()
        s.delete(s.get(User, uid))
        s.commit()
        assert s.scalars(select(UserAccount)).all() == []
        assert s.scalars(select(DeviceAccount)).all() == []
        assert s.scalars(select(Device)).one() is not None  # the computer stays


@pytest.mark.parametrize("value, expected", [
    (None, "legacy"), ("", "legacy"), ("legacy", "legacy"), ("device_accounts", "device_accounts"),
    (" Device_Accounts ", "device_accounts"), ("something else", "legacy"),
])
def test_signin_mode_defaults_to_legacy(monkeypatch, tmp_path, value, expected):
    monkeypatch.delenv(mode.ENV_NAME, raising=False)
    env = tmp_path / ".env"
    env.write_text("" if value is None else f"{mode.ENV_NAME}={value}\n", encoding="utf-8")
    assert mode.signin_mode(env) == expected


def test_environment_wins_over_the_env_file(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"{mode.ENV_NAME}=legacy\n", encoding="utf-8")
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    assert mode.signin_mode(env) == "device_accounts"


def test_missing_env_file_means_legacy(monkeypatch, tmp_path):
    monkeypatch.delenv(mode.ENV_NAME, raising=False)
    assert mode.signin_mode(tmp_path / "missing.env") == "legacy"
