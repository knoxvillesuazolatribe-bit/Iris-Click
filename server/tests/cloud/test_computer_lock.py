"""Computer lock on the website (app/cloud/computers.py, app/services/approved_computers.py)."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.cloud import access
from app.cloud import computers as routes
from app.cloud import main as cloud
from app.models.approved_computer import ApprovedComputer
from app.models.system_log import SystemLog
from app.services import approved_computers as computers

from tests.auth.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, admin_id, fresh_throttle, make_user  # noqa: F401

CODE = "test-access-code"
USER_AGENT_IP = {"x-real-ip": "198.51.100.7"}


@pytest.fixture
def site(monkeypatch):
    """The website with the access code still on; wrong-code waits recorded, not slept."""
    waits = []
    monkeypatch.setenv(access.CODE_ENV, CODE)
    monkeypatch.setattr(access, "sleep", waits.append)
    monkeypatch.setattr(access, "wrong_codes", access._WrongCodes())
    monkeypatch.setattr(routes, "wrong_codes", access._WrongCodes())
    return waits


@pytest.fixture
def lock(monkeypatch):
    monkeypatch.setenv(computers.LOCK_ENV, "on")


def computer():
    """One browser: its own cookies, with the access code entered."""
    c = TestClient(cloud.VercelPaths(cloud.create_app()), base_url="https://irisclick.example")
    assert c.post("/api/cloud/access", json={"code": CODE}).status_code == 200
    return c


@pytest.fixture
def office(site, admin_id):
    """The PDAO office computer, signed in as admin."""
    with computer() as c:
        assert c.post("/api/auth/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).status_code == 200
        yield c


@pytest.fixture
def home_pc(site):
    """The person's own computer."""
    with computer() as c:
        yield c


def link_for(office, user_id, label="Mari's laptop"):
    response = office.post(f"/api/admin/users/{user_id}/computers/link", json={"label": label})
    assert response.status_code == 200
    return response.json()


def names(client):
    response = client.get("/api/assistive/users")
    assert response.status_code == 200, response.text
    return [tile["full_name"] for tile in response.json()]


# --- Lock off: nothing changes -----------------------------------------------------------

def test_lock_off_name_screen_works_as_before(home_pc, make_user):
    ana = make_user("Ana Cruz")
    make_user("Ben Reyes")
    assert names(home_pc) == ["Ana Cruz", "Ben Reyes"]
    assert home_pc.post("/api/assistive/select", json={"user_id": ana}).status_code == 200


def test_lock_is_read_from_the_vercel_setting(monkeypatch):
    for value, expected in [("on", True), ("ON", True), ("1", True), ("true", True), ("yes", True),
                            ("", False), ("off", False), ("0", False)]:
        monkeypatch.setenv(computers.LOCK_ENV, value)
        assert computers.lock_on() is expected, value
    monkeypatch.delenv(computers.LOCK_ENV)
    assert computers.lock_on() is False


# --- Lock on -----------------------------------------------------------------------------

def test_unapproved_computer_sees_no_names(lock, home_pc, make_user):
    make_user("Ana Cruz")
    response = home_pc.get("/api/assistive/users")
    assert response.status_code == 403
    assert response.json() == {"detail": routes.NOT_APPROVED, "code": routes.NOT_APPROVED_CODE}


def test_unapproved_computer_cannot_pick_a_name(lock, home_pc, make_user):
    ana = make_user("Ana Cruz")
    response = home_pc.post("/api/assistive/select", json={"user_id": ana})
    assert response.status_code == 403 and response.json()["code"] == routes.NOT_APPROVED_CODE
    assert routes.COOKIE_NAME not in home_pc.cookies
    assert home_pc.get("/api/me/home").status_code == 401


def test_approval_link_opens_the_name_on_that_computer_only(lock, office, home_pc, make_user):
    ana = make_user("Ana Cruz")
    make_user("Ben Reyes")
    link = link_for(office, ana)
    assert link["path"] == f"/approve#{link['code']}"

    response = home_pc.post("/api/cloud/computers/claim", json={"code": link["code"]})
    assert response.status_code == 200 and response.json() == {"full_name": "Ana Cruz"}
    cookie = response.headers["set-cookie"]
    assert routes.COOKIE_NAME in cookie and "HttpOnly" in cookie and "Secure" in cookie
    assert "samesite=lax" in cookie.lower()

    assert names(home_pc) == ["Ana Cruz"]  # Ben is not approved here
    assert home_pc.post("/api/assistive/select", json={"user_id": ana}).status_code == 200
    assert home_pc.get("/api/me/home").json()["full_name"] == "Ana Cruz"


def test_other_names_stay_closed_on_an_approved_computer(lock, office, home_pc, make_user):
    ana = make_user("Ana Cruz")
    ben = make_user("Ben Reyes")
    home_pc.post("/api/cloud/computers/claim", json={"code": link_for(office, ana)["code"]})
    response = home_pc.post("/api/assistive/select", json={"user_id": ben})
    assert response.status_code == 403 and response.json()["detail"] == routes.NAME_NOT_APPROVED


def test_one_computer_can_be_approved_for_several_people(lock, office, home_pc, make_user):
    ana = make_user("Ana Cruz")
    ben = make_user("Ben Reyes")
    home_pc.post("/api/cloud/computers/claim", json={"code": link_for(office, ana)["code"]})
    key = home_pc.cookies[routes.COOKIE_NAME]
    home_pc.post("/api/cloud/computers/claim", json={"code": link_for(office, ben)["code"]})
    assert home_pc.cookies[routes.COOKIE_NAME] == key  # same computer key, two people
    assert names(home_pc) == ["Ana Cruz", "Ben Reyes"]


def test_a_link_works_only_once(lock, office, home_pc, site, make_user):
    ana = make_user("Ana Cruz")
    code = link_for(office, ana)["code"]
    assert home_pc.post("/api/cloud/computers/claim", json={"code": code}).status_code == 200
    with computer() as other:
        response = other.post("/api/cloud/computers/claim", json={"code": code})
        assert response.status_code == 401 and response.json()["detail"] == computers.LINK_NOT_VALID
        assert site == [access.WRONG_CODE_DELAY_S]
        assert other.get("/api/assistive/users").status_code == 403


def test_a_link_expires_after_24_hours(lock, office, home_pc, make_user, test_database):
    ana = make_user("Ana Cruz")
    code = link_for(office, ana)["code"]
    with test_database() as session:
        row = session.scalars(select(ApprovedComputer)).one()
        row.code_expires_at = row.code_expires_at - computers.LINK_LIFETIME - timedelta(seconds=1)
        session.commit()
    assert home_pc.post("/api/cloud/computers/claim", json={"code": code}).status_code == 401
    rows = office.get(f"/api/admin/users/{ana}/computers").json()["computers"]
    assert [r["status"] for r in rows] == [computers.STATUS_EXPIRED]


def test_wrong_codes_pause_that_address(office, home_pc, site):
    for _ in range(access.MAX_WRONG):
        response = home_pc.post("/api/cloud/computers/claim", json={"code": "not-a-real-code"},
                                headers=USER_AGENT_IP)
        assert response.status_code == 401
    response = home_pc.post("/api/cloud/computers/claim", json={"code": "not-a-real-code"},
                            headers=USER_AGENT_IP)
    assert response.status_code == 429
    assert len(site) == access.MAX_WRONG


def test_link_for_an_inactive_person_does_not_approve(lock, office, home_pc, make_user, test_database):
    from app.models.user import User
    ana = make_user("Ana Cruz")
    code = link_for(office, ana)["code"]
    with test_database() as session:
        session.get(User, ana).status = "inactive"
        session.commit()
    assert home_pc.post("/api/cloud/computers/claim", json={"code": code}).status_code == 409
    assert routes.COOKIE_NAME not in home_pc.cookies


def test_admin_can_approve_the_computer_they_are_on(lock, site, admin_id, make_user):
    ana = make_user("Ana Cruz")
    with computer() as pc:
        pc.post("/api/auth/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        response = pc.post(f"/api/admin/users/{ana}/computers/this", json={"label": "  Bedroom   PC "})
        assert response.status_code == 200
        body = response.json()
        assert body["label"] == "Bedroom PC" and body["status"] == "approved" and body["this_computer"]
        # Approving again on the same computer does not add a second row.
        assert pc.post(f"/api/admin/users/{ana}/computers/this", json={}).json()["computer_id"] == body["computer_id"]
        pc.post("/api/auth/logout")
        assert names(pc) == ["Ana Cruz"]


def test_admin_lists_and_removes_computers(lock, office, home_pc, make_user):
    ana = make_user("Ana Cruz")
    home_pc.post("/api/cloud/computers/claim", json={"code": link_for(office, ana)["code"]})
    link_for(office, ana, label="")  # a second link, still waiting

    listing = office.get(f"/api/admin/users/{ana}/computers").json()
    assert listing["lock_on"] is True
    rows = listing["computers"]
    assert [(r["label"], r["status"]) for r in rows] == [("Computer", "waiting"), ("Mari's laptop", "approved")]
    assert not any(r["this_computer"] for r in rows)  # the office computer is not one of them
    approved = rows[1]
    assert approved["approved_at"] and approved["last_used_at"]

    assert office.delete(f"/api/admin/users/{ana}/computers/{approved['computer_id']}").status_code == 204
    assert home_pc.get("/api/assistive/users").status_code == 403
    assert office.delete(f"/api/admin/users/{ana}/computers/{approved['computer_id']}").status_code == 404
    assert [r["status"] for r in office.get(f"/api/admin/users/{ana}/computers").json()["computers"]] == ["waiting"]


def test_a_removed_waiting_link_no_longer_works(lock, office, home_pc, make_user):
    ana = make_user("Ana Cruz")
    code = link_for(office, ana)["code"]
    row_id = office.get(f"/api/admin/users/{ana}/computers").json()["computers"][0]["computer_id"]
    office.delete(f"/api/admin/users/{ana}/computers/{row_id}")
    assert home_pc.post("/api/cloud/computers/claim", json={"code": code}).status_code == 401


def test_computers_are_admin_only(home_pc, make_user):
    ana = make_user("Ana Cruz")
    assert home_pc.get(f"/api/admin/users/{ana}/computers").status_code == 401
    assert home_pc.post(f"/api/admin/users/{ana}/computers/link", json={}).status_code == 401
    assert home_pc.post("/api/assistive/select", json={"user_id": ana}).status_code == 200
    assert home_pc.post(f"/api/admin/users/{ana}/computers/this", json={}).status_code == 403


def test_only_assistive_users_get_computers(office, admin_id):
    assert office.post(f"/api/admin/users/{admin_id}/computers/link", json={}).status_code == 404
    assert office.get("/api/admin/users/999999/computers").status_code == 404


def test_nothing_secret_is_stored_or_logged(lock, office, home_pc, make_user, test_database):
    ana = make_user("Ana Cruz")
    code = link_for(office, ana)["code"]
    home_pc.post("/api/cloud/computers/claim", json={"code": code})
    key = home_pc.cookies[routes.COOKIE_NAME]
    with test_database() as session:
        row = session.scalars(select(ApprovedComputer)).one()
        assert row.key_hash == computers.hash_secret(key) and row.code_hash is None
        stored = " ".join(str(v) for v in vars(row).values())
        logs = " ".join(f"{log.activity_type} {log.activity_description}" for log in session.scalars(select(SystemLog)))
    assert code not in stored and key not in stored
    assert code not in logs and key not in logs
    assert "computer_link_made" in logs and "computer_approved" in logs


def test_a_made_up_cookie_is_ignored(lock, home_pc, make_user):
    make_user("Ana Cruz")
    home_pc.cookies.set(routes.COOKIE_NAME, "x" * 43, domain="irisclick.example")
    assert home_pc.get("/api/assistive/users").status_code == 403
    assert computers.usable_key("short") is None
    assert computers.usable_key("bad key with spaces and more than forty characters!!") is None


def test_claim_works_without_the_access_code(lock, office, make_user):
    """The approval link may be the first thing a new computer opens."""
    ana = make_user("Ana Cruz")
    code = link_for(office, ana)["code"]
    with TestClient(cloud.VercelPaths(cloud.create_app()), base_url="https://irisclick.example") as fresh:
        assert fresh.post("/api/cloud/computers/claim", json={"code": code}).status_code == 200


def test_setup_check_needs_an_admin_when_the_lock_is_on(lock, office, home_pc):
    assert home_pc.get("/api/cloud/check").status_code == 401
    assert office.get("/api/cloud/check").status_code == 200
