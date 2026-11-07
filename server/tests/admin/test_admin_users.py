"""Admin access, dashboard and user management (Phase 8)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models.sos import SosHistory
from app.models.timestamps import utc_now
from app.models.user import User
from app.models.user_session import UserSession
from app.services import active_user

from tests.admin.conftest import add_calibration, logs, sign_in_as

ADMIN_ENDPOINTS = [
    ("get", "/api/admin/dashboard"), ("get", "/api/admin/logs"),
    ("get", "/api/admin/reports/sos"), ("get", "/api/admin/reports/sos/pdf"),
    ("get", "/api/admin/settings/defaults"), ("post", "/api/admin/settings/defaults/reset"),
    ("get", "/api/admin/settings/system"), ("post", "/api/admin/settings/system/test-sms"),
    ("get", "/api/admin/users/1"), ("post", "/api/admin/users/1/settings/reset"),
    ("delete", "/api/admin/users/1/contacts/1"),
]


@pytest.mark.parametrize(("method", "path"), ADMIN_ENDPOINTS)
def test_admin_pages_need_an_admin(api, make_user, env, method, path):
    assert getattr(api, method)(path).status_code == 401
    sign_in_as(api, make_user("Ana Cruz"))
    assert getattr(api, method)(path).status_code == 403


def test_app_info_is_public(api, env):
    assert api.get("/api/app-info").json() == {"app_name": "IrisClick"}


# --- Dashboard ------------------------------------------------------------------------------

def test_dashboard_counts_are_real(admin, make_user, test_database):
    ana = make_user("Ana Cruz")
    make_user("Ben Reyes")
    make_user("Gone Person", status="inactive")
    add_calibration(test_database, ana, file_id="a")
    add_calibration(test_database, ana, file_id="old", when=utc_now() - timedelta(days=30))
    add_calibration(test_database, ana, status="Failed")
    with test_database() as session:
        for activation, days_ago in (("one", 1), ("one", 1), ("two", 20)):
            session.add(SosHistory(user_id=ana, activation_id=activation, channel="email",
                                   message_sent="SOS", status="sent",
                                   date_sent=utc_now() - timedelta(days=days_ago)))
        session.commit()
    body = admin.get("/api/admin/dashboard").json()
    assert body == {"active_users": 2, "active_users_week": 0, "sos_events": 2,
                    "sos_events_week": 1, "calibrations": 2, "calibrations_week": 1}


# --- Users ------------------------------------------------------------------------------------

def test_list_includes_calibration_summary(admin, make_user, test_database):
    ana = make_user("Ana Cruz")
    add_calibration(test_database, ana, file_id="a", accuracy="91.20")
    rows = {u["full_name"]: u for u in admin.get("/api/admin/users").json()}
    assert rows["Ana Cruz"]["calibration_count"] == 1
    assert float(rows["Ana Cruz"]["latest_accuracy"]) == 91.2
    assert rows["PDAO Admin"]["role"] == "admin"


def test_detail_shows_profile_settings_and_contacts(admin, make_user):
    ana = make_user("Ana Cruz")
    body = admin.get(f"/api/admin/users/{ana}").json()
    assert body["user"]["full_name"] == "Ana Cruz"
    assert body["settings"]["is_default"] is True
    assert body["contacts"] == [] and body["sos_location"] is None


def test_admin_accounts_are_not_managed_here(admin, admin_id):
    assert admin.get(f"/api/admin/users/{admin_id}").status_code == 404
    assert admin.post(f"/api/admin/users/{admin_id}/status",
                      json={"status": "inactive"}).status_code == 404


def test_update_profile_sets_the_sos_location(admin, make_user, test_database):
    ana = make_user("Ana Cruz")
    changed = admin.put(f"/api/admin/users/{ana}", json={
        "full_name": " Ana M. Cruz ", "address": "12 Mabini St.", "barangay": "Pajo"}).json()
    assert changed["full_name"] == "Ana M. Cruz"
    detail = admin.get(f"/api/admin/users/{ana}").json()
    assert detail["sos_location"] == "12 Mabini St., Barangay Pajo, Lapu-Lapu City"
    assert "PDAO Admin updated the profile of Ana M. Cruz" in \
        logs(test_database, "user_updated")[0].activity_description


def test_deactivate_ends_sign_in_and_hides_the_tile(api, make_user, admin_id, env, test_database):
    from tests.admin.conftest import ADMIN_EMAIL, ADMIN_PASSWORD
    from fastapi.testclient import TestClient

    from app.api.main import create_app

    ana = make_user("Ana Cruz")
    sign_in_as(api, ana)
    assert api.get("/api/auth/me").json()["full_name"] == "Ana Cruz"
    assert active_user.get_user_id() == ana

    with TestClient(create_app()) as admin:
        admin.post("/api/auth/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        row = admin.post(f"/api/admin/users/{ana}/status", json={"status": "inactive"}).json()
        assert row["status"] == "inactive"
        assert "Ana Cruz" not in [t["full_name"] for t in admin.get("/api/assistive/users").json()]
        assert admin.post("/api/assistive/select", json={"user_id": ana}).status_code == 403

        assert api.get("/api/me/home").status_code == 401  # her sign-in has ended
        assert active_user.get_user_id() is None
        with test_database() as session:
            assert all(s.revoked_at is not None for s in session.scalars(
                select(UserSession).where(UserSession.user_id == ana)))
        assert "ended 1 sign-in" in logs(test_database, "user_deactivated")[0].activity_description

        admin.post(f"/api/admin/users/{ana}/status", json={"status": "active"})
        assert len(logs(test_database, "user_reactivated")) == 1
        with test_database() as session:
            assert session.get(User, ana).status == "active"


# --- Settings and contacts edited by the admin ----------------------------------------------

SETTINGS = {"dwell_enabled": True, "dwell_ms": 900, "smoothing": "low", "blink_to_click": True,
            "blink_sensitivity": 2, "edge_scroll_enabled": False, "voice_volume": 70}


def test_admin_edits_a_users_settings(admin, make_user, test_database):
    ana = make_user("Ana Cruz")
    saved = admin.put(f"/api/admin/users/{ana}/settings", json=SETTINGS).json()
    assert saved["dwell_ms"] == 900 and saved["is_default"] is False
    assert "saved by PDAO Admin" in logs(test_database, "settings_updated")[0].activity_description
    assert admin.put(f"/api/admin/users/{ana}/settings",
                     json={**SETTINGS, "dwell_enabled": False, "blink_to_click": False}
                     ).status_code == 422
    reset = admin.post(f"/api/admin/users/{ana}/settings/reset").json()
    assert reset["is_default"] is True
    assert "reset to default by PDAO Admin" in \
        logs(test_database, "settings_reset")[0].activity_description


def test_admin_manages_a_users_contacts(admin, make_user, test_database):
    ana = make_user("Ana Cruz")
    contact = admin.post(f"/api/admin/users/{ana}/contacts", json={
        "contact_name": "Maria Cruz", "email_address": "maria@example.com"}).json()
    admin.put(f"/api/admin/users/{ana}/contacts/{contact['contact_id']}",
              json={"contact_name": "Maria C.", "email_address": "maria@example.com"})
    assert [c["contact_name"] for c in admin.get(f"/api/admin/users/{ana}").json()["contacts"]] \
        == ["Maria C."]
    assert admin.delete(f"/api/admin/users/{ana}/contacts/{contact['contact_id']}").status_code == 204
    added = logs(test_database, "sos_contact_added")[0]
    assert added.activity_description == "Emergency contact added for Ana Cruz by PDAO Admin"
    ben = make_user("Ben Reyes")
    other = admin.post(f"/api/admin/users/{ben}/contacts", json={
        "contact_name": "X", "email_address": "x@y.co"}).json()
    assert admin.delete(f"/api/admin/users/{ana}/contacts/{other['contact_id']}").status_code == 404
