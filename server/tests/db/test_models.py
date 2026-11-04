import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.models import accessibility_settings as settings_model
from app.models.all_models import (
    AccessibilitySettings,
    CalibrationRecord,
    CommunicationHistory,
    SosContact,
    SosHistory,
    SystemLog,
    User,
)


def _assistive(session, name="Ana Cruz"):
    user = User(full_name=name, role="assistive_user", barangay="Pajo")
    session.add(user)
    session.flush()
    return user


def test_assistive_user_needs_no_email_or_password(test_database):
    with test_database() as session:
        user = _assistive(session)
        session.commit()
        assert user.status == "active"
        assert user.created_at is not None


def test_admin_requires_email_and_password_hash(test_database):
    with test_database() as session:
        session.add(User(full_name="PDAO Staff", role="admin"))
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize("field, value", [("role", "guest"), ("status", "deleted")])
def test_role_and_status_are_restricted(test_database, field, value):
    with test_database() as session:
        user = User(full_name="X", role="assistive_user")
        setattr(user, field, value)
        session.add(user)
        with pytest.raises(IntegrityError):
            session.commit()


def test_email_is_unique(test_database):
    with test_database() as session:
        for _ in range(2):
            session.add(User(full_name="Admin", role="admin", email="a@pdao.ph", password_hash="h"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_accessibility_defaults_match_current_worker_settings():
    defaults = Settings.model_fields
    assert settings_model.DEFAULT_DWELL_ENABLED == defaults["dwell_click_enabled"].default
    assert settings_model.DEFAULT_DWELL_MS == defaults["dwell_ms"].default
    assert settings_model.DEFAULT_CURSOR_SMOOTHING == defaults["cursor_smoothing"].default
    assert settings_model.DEFAULT_BLINK_SENSITIVITY == defaults["blink_threshold"].default


def test_settings_row_gets_defaults_and_numeric_blink_sensitivity(test_database):
    with test_database() as session:
        user = _assistive(session)
        session.add(AccessibilitySettings(user_id=user.user_id))
        session.commit()
        row = session.scalars(select(AccessibilitySettings)).one()
    assert (row.dwell_enabled, row.dwell_ms, row.blink_to_click, row.voice_volume) == (
        False, 700, True, 100)
    assert isinstance(row.blink_sensitivity, float) and row.blink_sensitivity == 0.18


@pytest.mark.parametrize("field, value", [
    ("dwell_ms", 399), ("dwell_ms", 1501), ("cursor_smoothing", 1.5),
    ("blink_sensitivity", 0.5), ("voice_volume", 101),
])
def test_settings_out_of_range_are_rejected(test_database, field, value):
    with test_database() as session:
        user = _assistive(session)
        session.add(AccessibilitySettings(user_id=user.user_id, **{field: value}))
        with pytest.raises(IntegrityError):
            session.commit()


def test_one_settings_row_per_user(test_database):
    with test_database() as session:
        user = _assistive(session)
        session.add_all([AccessibilitySettings(user_id=user.user_id),
                         AccessibilitySettings(user_id=user.user_id)])
        with pytest.raises(IntegrityError):
            session.commit()


def test_sos_contact_needs_a_number_or_email(test_database):
    with test_database() as session:
        user = _assistive(session)
        session.add(SosContact(user_id=user.user_id, contact_name="Mama"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_deleting_a_user_removes_personal_rows_but_keeps_logs(test_database):
    with test_database() as session:
        user = _assistive(session)
        uid = user.user_id
        session.add_all([
            AccessibilitySettings(user_id=uid),
            CalibrationRecord(user_id=uid, profile_name="Desk", status="Successful"),
            CommunicationHistory(user_id=uid, mode="text_to_speech", message="I need help"),
            SosContact(user_id=uid, contact_name="Mama", contact_number="09170000000"),
            SystemLog(user_id=uid, activity_type="login"),
        ])
        session.commit()
        session.delete(user)
        session.commit()
        session.expire_all()
        for model in (AccessibilitySettings, CalibrationRecord, CommunicationHistory, SosContact):
            assert session.scalars(select(model)).all() == []
        log = session.scalars(select(SystemLog)).one()
        assert log.user_id is None


def test_sos_history_survives_contact_deletion(test_database):
    with test_database() as session:
        user = _assistive(session)
        contact = SosContact(user_id=user.user_id, contact_name="Mama", email_address="m@x.ph")
        session.add(contact)
        session.flush()
        session.add(SosHistory(user_id=user.user_id, contact_id=contact.contact_id,
                               activation_id="a1", channel="email", recipient="m@x.ph",
                               message_sent="Help", status="sent"))
        session.commit()
        session.delete(contact)
        session.commit()
        session.expire_all()
        history = session.scalars(select(SosHistory)).one()
    assert history.contact_id is None and history.recipient == "m@x.ph"


def test_sos_and_communication_values_are_restricted(test_database):
    with test_database() as session:
        user = _assistive(session)
        session.add(CommunicationHistory(user_id=user.user_id, mode="telepathy", message="x"))
        with pytest.raises(IntegrityError):
            session.commit()
