"""Voice Communication routes (Phase 4)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.accessibility_settings import AccessibilitySettings
from app.models.communication import CommunicationHistory

from tests.auth.conftest import (  # noqa: F401  (fixtures)
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    admin_id,
    api,
    fresh_throttle,
    logs,
    make_user,
    profiles_dir,
    signed_in_admin,
)


def _sign_in(api, user_id):
    assert api.post("/api/assistive/select", json={"user_id": user_id}).status_code == 200


@pytest.fixture
def ana(api, make_user):
    user_id = make_user("Ana Cruz")
    _sign_in(api, user_id)
    return user_id


def _send(api, message, mode="text_to_speech"):
    return api.post("/api/me/communications", json={"mode": mode, "message": message})


def _messages(factory, user_id=None):
    with factory() as session:
        query = select(CommunicationHistory).order_by(CommunicationHistory.communication_id)
        if user_id is not None:
            query = query.where(CommunicationHistory.user_id == user_id)
        return session.scalars(query).all()


# --- Access ------------------------------------------------------------------

def test_signed_out_visitors_are_turned_away(api):
    assert api.get("/api/me/voice").status_code == 401
    assert _send(api, "Hello").status_code == 401
    assert api.delete("/api/me/communications/1").status_code == 401


def test_admins_cannot_use_voice_pages(signed_in_admin):
    assert signed_in_admin.get("/api/me/voice").status_code == 403
    assert _send(signed_in_admin, "Hello").status_code == 403


# --- Volume ------------------------------------------------------------------

def test_volume_defaults_to_full(api, ana):
    body = api.get("/api/me/voice").json()
    assert body == {"voice_volume": 100, "messages": []}


def test_volume_comes_from_the_users_settings(api, ana, test_database):
    with test_database() as session:
        session.add(AccessibilitySettings(user_id=ana, voice_volume=40))
        session.commit()
    assert api.get("/api/me/voice").json()["voice_volume"] == 40


# --- Sending -----------------------------------------------------------------

def test_send_saves_trimmed_message_and_logs_without_text(api, ana, test_database):
    response = _send(api, "  I need water  ")
    assert response.status_code == 201
    body = response.json()
    assert body["message"] == "I need water"
    assert body["mode"] == "text_to_speech"

    saved = _messages(test_database)
    assert [(m.user_id, m.mode, m.message) for m in saved] == [(ana, "text_to_speech", "I need water")]
    sent = logs(test_database, "communication_sent")
    assert len(sent) == 1
    assert "I need water" not in sent[0].activity_description
    assert "text-to-speech message (12 characters)" in sent[0].activity_description


def test_speech_to_text_messages_are_saved(api, ana, test_database):
    assert _send(api, "Good morning", mode="speech_to_text").status_code == 201
    assert _messages(test_database)[0].mode == "speech_to_text"
    assert "speech-to-text" in logs(test_database, "communication_sent")[0].activity_description


@pytest.mark.parametrize("message", ["", "   ", "\n\t "])
def test_empty_messages_are_refused(api, ana, test_database, message):
    assert _send(api, message).status_code == 422
    assert _messages(test_database) == []


def test_long_messages_are_capped(api, ana, test_database):
    assert _send(api, "a" * 1000).status_code == 201
    assert _send(api, "a" * 1001).status_code == 422
    assert len(_messages(test_database)) == 1


def test_unknown_mode_is_refused(api, ana):
    assert _send(api, "Hello", mode="shouting").status_code == 422


def test_history_lists_only_my_latest_ten_newest_first(api, ana, make_user, test_database):
    ben = make_user("Ben Reyes")
    start = datetime(2026, 11, 1, tzinfo=UTC)
    with test_database() as session:
        for i in range(12):
            session.add(CommunicationHistory(user_id=ana, mode="text_to_speech",
                                             message=f"ana {i}",
                                             date_created=start + timedelta(minutes=i)))
        session.add(CommunicationHistory(user_id=ben, mode="text_to_speech", message="ben",
                                         date_created=start + timedelta(days=1)))
        session.commit()
    messages = api.get("/api/me/voice").json()["messages"]
    assert [m["message"] for m in messages] == [f"ana {i}" for i in range(11, 1, -1)]


# --- Deleting ----------------------------------------------------------------

def test_delete_my_message(api, ana, test_database):
    message_id = _send(api, "Yes").json()["communication_id"]
    assert api.delete(f"/api/me/communications/{message_id}").status_code == 204
    assert _messages(test_database) == []
    deleted = logs(test_database, "communication_deleted")
    assert len(deleted) == 1 and deleted[0].user_id == ana
    assert api.delete(f"/api/me/communications/{message_id}").status_code == 404


def test_cannot_delete_someone_elses_message(api, ana, make_user, test_database):
    ben = make_user("Ben Reyes")
    with test_database() as session:
        row = CommunicationHistory(user_id=ben, mode="text_to_speech", message="ben's")
        session.add(row)
        session.commit()
        bens_id = row.communication_id
    assert api.delete(f"/api/me/communications/{bens_id}").status_code == 404
    assert len(_messages(test_database, ben)) == 1
    assert logs(test_database, "communication_deleted") == []
