"""Emergency SOS routes (Phase 5): contacts, activation, retries, status."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models.sos import SosHistory
from app.models.timestamps import utc_now
from app.models.user import User
from app.services import sos_service
from app.services.sos_delivery import CANNOT_REACH, EMAIL_NOT_SET_UP, SMS_NOT_SET_UP, DeliveryError
from app.services.sos_dispatcher import dispatcher

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


class FakeEmail:
    """Scripted email channel: per recipient, a list of outcomes (None = sent)."""

    def __init__(self, script=None):
        self.script = script or {}
        self.sent: list[tuple[str, str, str]] = []
        self.calls: list[str] = []

    def configured(self):
        return True

    def send(self, to, subject, body):
        self.calls.append(to)
        outcomes = self.script.get(to, [])
        outcome = outcomes.pop(0) if outcomes else None
        if outcome is not None:
            raise outcome
        self.sent.append((to, subject, body))


@pytest.fixture
def email(monkeypatch):
    fake = FakeEmail()
    monkeypatch.setattr(dispatcher, "inline", True)
    monkeypatch.setattr(dispatcher, "delays", (0.0, 0.0, 0.0))
    monkeypatch.setattr(dispatcher, "sleep", lambda _s: None)
    monkeypatch.setattr(dispatcher, "email_factory", lambda: fake)
    no_smtp = get_settings().model_copy(update={"smtp_host": "", "smtp_from": "",
                                                "smtp_username": ""})
    monkeypatch.setattr(sos_service, "get_settings", lambda: no_smtp)
    return fake


def _sign_in(api, user_id):
    assert api.post("/api/assistive/select", json={"user_id": user_id}).status_code == 200


@pytest.fixture
def ana(api, make_user, test_database, email):
    user_id = make_user("Ana Cruz")
    with test_database() as session:
        user = session.get(User, user_id)
        user.address, user.barangay = "12 Mabini St.", "Pajo"
        session.commit()
    _sign_in(api, user_id)
    return user_id


def _add(api, name="Maria Cruz", number=None, email_address="maria@example.com", relationship="Mother"):
    return api.post("/api/me/sos/contacts", json={
        "contact_name": name, "contact_number": number, "email_address": email_address,
        "relationship": relationship})


def _activate(api, activation_id=None):
    return api.post("/api/me/sos/activate", json={"activation_id": str(activation_id or uuid.uuid4())})


def _rows(factory):
    with factory() as session:
        return session.scalars(select(SosHistory).order_by(SosHistory.sos_id)).all()


# --- Access ------------------------------------------------------------------

def test_signed_out_visitors_are_turned_away(api, email):
    assert api.get("/api/me/sos").status_code == 401
    assert _activate(api).status_code == 401


def test_admins_cannot_use_the_user_sos_pages(signed_in_admin, email):
    assert signed_in_admin.get("/api/me/sos").status_code == 403
    assert _activate(signed_in_admin).status_code == 403


# --- Contacts ----------------------------------------------------------------

def test_add_edit_delete_contact_with_logs(api, ana, test_database):
    created = _add(api, number="+63 917 123 4567", email_address="  Maria@Example.com ")
    assert created.status_code == 201
    contact = created.json()
    assert contact["email_address"] == "maria@example.com"
    assert contact["contact_number"] == "+63 917 123 4567"

    changed = api.put(f"/api/me/sos/contacts/{contact['contact_id']}", json={
        "contact_name": "Maria C.", "contact_number": "", "email_address": "maria@example.com",
        "relationship": ""}).json()
    assert changed["contact_name"] == "Maria C."
    assert changed["contact_number"] is None and changed["relationship"] is None

    assert api.delete(f"/api/me/sos/contacts/{contact['contact_id']}").status_code == 204
    assert api.get("/api/me/sos/contacts").json() == []
    for kind in ("sos_contact_added", "sos_contact_updated", "sos_contact_deleted"):
        assert len(logs(test_database, kind)) == 1


@pytest.mark.parametrize("body", [
    {"contact_name": "No way to reach", "contact_number": "", "email_address": ""},
    {"contact_name": "", "email_address": "a@b.co"},
    {"contact_name": "Bad email", "email_address": "not-an-email"},
    {"contact_name": "Bad number", "contact_number": "call me"},
])
def test_contact_validation(api, ana, body):
    assert api.post("/api/me/sos/contacts", json=body).status_code == 422


def test_phone_only_contacts_are_allowed(api, ana):
    assert _add(api, number="09171234567", email_address=None).status_code == 201


def test_contact_limit(api, ana):
    for i in range(sos_service.MAX_CONTACTS):
        assert _add(api, name=f"Contact {i}").status_code == 201
    response = _add(api, name="One too many")
    assert response.status_code == 409


def test_cannot_touch_someone_elses_contact(api, ana, make_user, test_database):
    contact_id = _add(api).json()["contact_id"]
    _sign_in(api, make_user("Ben Reyes"))
    assert api.put(f"/api/me/sos/contacts/{contact_id}",
                   json={"contact_name": "X", "email_address": "x@y.co"}).status_code == 404
    assert api.delete(f"/api/me/sos/contacts/{contact_id}").status_code == 404
    assert api.get("/api/me/sos/contacts").json() == []


# --- Overview and location -----------------------------------------------------

def test_overview_shows_location_and_email_status(api, ana):
    _add(api)
    body = api.get("/api/me/sos").json()
    assert body["location_text"] == "12 Mabini St., Barangay Pajo, Lapu-Lapu City"
    assert body["email_configured"] is False
    assert body["sms_configured"] is False
    assert [c["contact_name"] for c in body["contacts"]] == ["Maria Cruz"]


def test_location_is_none_without_address():
    user = User(full_name="X", role="assistive_user", address=" ", barangay=None)
    assert sos_service.location_text(user) is None
    user.barangay = "Brgy. Gun-ob"
    assert sos_service.location_text(user) == "Brgy. Gun-ob, Lapu-Lapu City"


# --- Activation ----------------------------------------------------------------

def test_no_contacts_cannot_send(api, ana, test_database):
    response = _activate(api)
    assert response.status_code == 409
    assert response.json()["detail"] == sos_service.NO_CONTACTS
    assert _rows(test_database) == []


def test_sends_one_alert_per_contact(api, ana, email, test_database):
    _add(api, name="Maria Cruz", email_address="maria@example.com")
    _add(api, name="Jose Cruz", number="09171234567", email_address=None, relationship="Father")
    view = _activate(api).json()

    assert (view["total"], view["sent"], view["failed"], view["pending"]) == (2, 1, 1, 0)
    by_name = {a["contact_name"]: a for a in view["alerts"]}
    assert by_name["Maria Cruz"]["status"] == "sent"
    assert by_name["Maria Cruz"]["channel"] == "email"
    assert by_name["Jose Cruz"]["status"] == "failed"
    assert by_name["Jose Cruz"]["channel"] == "sms"
    assert by_name["Jose Cruz"]["detail"] == SMS_NOT_SET_UP
    assert view["location_text"] == "12 Mabini St., Barangay Pajo, Lapu-Lapu City"

    to, subject, body = email.sent[0]
    assert to == "maria@example.com"
    assert subject == "EMERGENCY SOS: Ana Cruz needs help."
    assert "12 Mabini St., Barangay Pajo, Lapu-Lapu City" in body

    rows = _rows(test_database)
    assert len(rows) == 2 and len({r.activation_id for r in rows}) == 1
    assert len(logs(test_database, "sos_activated")) == 1
    assert "1 sent, 1 failed" in logs(test_database, "sos_delivery")[0].activity_description


def test_temporary_failures_are_retried_then_sent(api, ana, email, monkeypatch, test_database):
    _add(api)
    offline = DeliveryError(CANNOT_REACH, retryable=True)
    email.script["maria@example.com"] = [offline, offline]
    seen_while_retrying = []
    monkeypatch.setattr(dispatcher, "sleep",
                        lambda _s: seen_while_retrying.append(_rows(test_database)[0].error_detail))

    view = _activate(api).json()
    assert view["alerts"][0]["status"] == "sent"
    assert view["alerts"][0]["detail"] is None
    assert len(email.calls) == 3
    assert seen_while_retrying[0].startswith("Not sent yet, retrying (attempt 1 of 4 failed).")


def test_gives_up_after_three_retries(api, ana, email):
    _add(api)
    email.script["maria@example.com"] = [DeliveryError(CANNOT_REACH, retryable=True)] * 5
    alert = _activate(api).json()["alerts"][0]
    assert alert["status"] == "failed"
    assert alert["detail"] == f"{CANNOT_REACH} Gave up after 4 attempts."
    assert len(email.calls) == 4


def test_permanent_failures_are_not_retried(api, ana, email):
    _add(api)
    email.script["maria@example.com"] = [DeliveryError("Password refused.", retryable=False)]
    alert = _activate(api).json()["alerts"][0]
    assert (alert["status"], alert["detail"]) == ("failed", "Password refused.")
    assert len(email.calls) == 1


def test_email_not_set_up_is_shown_as_failed(api, ana, monkeypatch):
    from app.services.sos_delivery import EmailSender
    no_smtp = get_settings().model_copy(update={"smtp_host": "", "smtp_from": "", "smtp_username": ""})
    monkeypatch.setattr(dispatcher, "email_factory", lambda: EmailSender(no_smtp))
    _add(api)
    view = _activate(api).json()
    assert (view["sent"], view["failed"]) == (0, 1)
    assert view["alerts"][0]["detail"] == EMAIL_NOT_SET_UP


def test_double_activation_is_guarded(api, ana, email, test_database):
    _add(api)
    first = uuid.uuid4()
    assert _activate(api, first).json()["activation_id"] == str(first)
    assert _activate(api, first).json()["activation_id"] == str(first)
    assert _activate(api).json()["activation_id"] == str(first)  # new press within 60 s
    assert len(_rows(test_database)) == 1
    assert len(email.sent) == 1
    assert len(logs(test_database, "sos_activated")) == 1


def test_a_fully_failed_sos_can_be_sent_again(api, ana, email, test_database):
    _add(api)
    email.script["maria@example.com"] = [DeliveryError("Refused.", retryable=False)]
    first = _activate(api).json()["activation_id"]
    second = _activate(api).json()
    assert second["activation_id"] != first
    assert second["sent"] == 1


def test_activation_belongs_to_its_user(api, ana, make_user):
    _add(api)
    activation_id = _activate(api).json()["activation_id"]
    _sign_in(api, make_user("Ben Reyes"))
    assert api.get(f"/api/me/sos/activations/{activation_id}").status_code == 404
    assert _activate(api, activation_id).status_code == 409


def test_pending_alerts_left_by_a_restart_show_as_failed(api, ana, test_database):
    activation_id = str(uuid.uuid4())
    with test_database() as session:
        session.add(SosHistory(user_id=ana, activation_id=activation_id, channel="email",
                               recipient="maria@example.com", message_sent="EMERGENCY SOS",
                               status="pending", date_sent=utc_now() - timedelta(minutes=10)))
        session.commit()
    alert = api.get(f"/api/me/sos/activations/{activation_id}").json()["alerts"][0]
    assert (alert["status"], alert["detail"]) == ("failed", sos_service.STOPPED_BY_RESTART)


def test_cancel_is_logged_and_sends_nothing(api, ana, email, test_database):
    _add(api)
    assert api.post("/api/me/sos/cancel").status_code == 204
    assert _rows(test_database) == []
    assert email.calls == []
    assert len(logs(test_database, "sos_cancelled")) == 1
