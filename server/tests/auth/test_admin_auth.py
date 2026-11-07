from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.models import database
from app.models.timestamps import utc_now
from app.models.user import User
from app.models.user_session import UserSession
from app.services import auth_service
from app.services.password_hashing import hash_password, needs_rehash, verify_password
from app.services.session_service import COOKIE_NAME, hash_token

from tests.auth.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, logs


def _login(api, email=ADMIN_EMAIL, password=ADMIN_PASSWORD):
    return api.post("/api/auth/admin/login", json={"email": email, "password": password})


def test_password_hashing_round_trip():
    hashed = hash_password("a long passphrase")
    assert hashed.startswith("$argon2id$") and "a long passphrase" not in hashed
    assert verify_password(hashed, "a long passphrase")
    assert not verify_password(hashed, "wrong")
    assert not verify_password(None, "anything")
    assert not verify_password("not-a-hash", "anything")
    assert not needs_rehash(hashed)


def test_admin_login_sets_an_httponly_session_cookie(api, admin_id, test_database):
    response = _login(api, email="  ADMIN@pdao.ph ")

    assert response.status_code == 200
    assert response.json() == {"user_id": admin_id, "full_name": "PDAO Admin", "role": "admin"}
    cookie = response.headers["set-cookie"]
    assert COOKIE_NAME in cookie and "HttpOnly" in cookie and "Path=/api" in cookie
    assert "samesite=lax" in cookie.lower()
    assert api.get("/api/auth/me").json()["role"] == "admin"
    [log] = logs(test_database, "login")
    assert log.user_id == admin_id


def test_only_a_hash_of_the_token_is_stored(api, admin_id, test_database):
    _login(api)
    token = api.cookies.get(COOKIE_NAME)
    with test_database() as session:
        row = session.scalars(select(UserSession)).one()
    assert row.token_hash == hash_token(token) and token not in row.token_hash


def test_wrong_password_is_refused_then_retry_works(api, admin_id, test_database):
    wrong = _login(api, password="nope")
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == auth_service.INVALID_MESSAGE
    assert api.get("/api/auth/me").status_code == 401
    assert _login(api).status_code == 200
    assert len(logs(test_database, "login_failed")) == 1


def test_unknown_email_gets_the_same_message(api, admin_id):
    response = _login(api, email="nobody@pdao.ph")
    assert response.status_code == 401
    assert response.json()["detail"] == auth_service.INVALID_MESSAGE


def test_assistive_users_cannot_use_the_admin_login(api, make_user):
    make_user("Ana", email="ana@pdao.ph", password="a long passphrase")
    assert _login(api, email="ana@pdao.ph", password="a long passphrase").status_code == 401


def test_inactive_admin_cannot_sign_in(api, make_user):
    make_user("Old Admin", role="admin", status="inactive", email="old@pdao.ph",
              password=ADMIN_PASSWORD)
    response = _login(api, email="old@pdao.ph")
    assert response.status_code == 403
    assert response.json()["detail"] == auth_service.INACTIVE_MESSAGE


def test_repeated_failures_lock_the_email(api, admin_id):
    for _ in range(auth_service.MAX_FAILURES):
        assert _login(api, password="nope").status_code == 401
    locked = _login(api)  # even the right password waits out the lockout
    assert locked.status_code == 429
    assert "Too many attempts" in locked.json()["detail"]


def test_lockout_ends_after_the_lockout_time():
    now = [0.0]
    throttle = auth_service.LoginThrottle(clock=lambda: now[0])
    for _ in range(auth_service.MAX_FAILURES):
        throttle.failed("a@b.c")
    assert throttle.seconds_locked("a@b.c") > 0
    now[0] += auth_service.LOCKOUT_S + 1
    assert throttle.seconds_locked("a@b.c") == 0


def test_logout_ends_the_session(api, admin_id, test_database):
    _login(api)
    token = api.cookies.get(COOKIE_NAME)
    assert api.post("/api/auth/logout").status_code == 204
    api.cookies.set(COOKIE_NAME, token, path="/api")  # replaying the old cookie fails
    assert api.get("/api/auth/me").status_code == 401
    assert len(logs(test_database, "logout")) == 1


def test_expired_session_is_refused(api, admin_id, test_database):
    _login(api)
    with test_database() as session:
        session.scalars(select(UserSession)).one().expires_at = utc_now() - timedelta(minutes=1)
        session.commit()
    assert api.get("/api/auth/me").status_code == 401


def test_deactivating_a_user_ends_their_session(api, admin_id, test_database):
    _login(api)
    with test_database() as session:
        session.get(User, admin_id).status = "inactive"
        session.commit()
    assert api.get("/api/auth/me").status_code == 401


def test_admin_routes_need_an_admin(api, make_user):
    assert api.get("/api/admin/users").status_code == 401
    user_id = make_user("Ana Cruz")
    api.post("/api/assistive/select", json={"user_id": user_id})
    assert api.get("/api/admin/users").status_code == 403


def test_admin_creates_and_lists_assistive_users(signed_in_admin, admin_id, test_database):
    created = signed_in_admin.post("/api/admin/users",
                                   json={"full_name": "  Ben Reyes ", "barangay": "Pusok"})
    assert created.status_code == 201
    body = created.json()
    assert (body["full_name"], body["role"], body["status"], body["barangay"]) == (
        "Ben Reyes", "assistive_user", "active", "Pusok")
    names = [u["full_name"] for u in signed_in_admin.get("/api/admin/users").json()]
    assert "Ben Reyes" in names and "PDAO Admin" in names
    [log] = logs(test_database, "user_created")
    assert log.user_id == admin_id and "Ben Reyes" in log.activity_description


def test_blank_name_is_rejected(signed_in_admin):
    assert signed_in_admin.post("/api/admin/users", json={"full_name": "   "}).status_code == 422


def test_database_down_gives_a_clear_503(api, monkeypatch):
    def down():
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(database, "get_session_factory", down)
    response = _login(api)
    assert response.status_code == 503
    assert "Eye tracking still works" in response.json()["detail"]
    assert api.get("/api/health").status_code == 200  # the rest of the API is unaffected
