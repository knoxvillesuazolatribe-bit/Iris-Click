"""Web ↔ desktop link: Origin guard, signed tokens, hosted and desktop link routes."""

import time

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from app.api.origin_guard import OriginGuard
from app.api.routes import desktop_link
from app.cloud import desktop as cloud_desktop
from app.config import get_settings
from app.services import active_user, desktop_tokens
from app.services.desktop_tokens import DESKTOP, LINK, TokenError

from tests.auth.conftest import fresh_throttle, make_user  # noqa: F401  (fixtures)

SITE = "https://iris-click.example.app"
EVIL = "https://evil.example.com"


# --- Origin guard ------------------------------------------------------------------------------

def guarded_app():
    inner = FastAPI()

    @inner.post("/api/tracking/start")
    def start():
        return {"started": True}

    @inner.websocket("/api/ws/calibration")
    async def ws(socket: WebSocket):
        await socket.accept()
        await socket.send_text("hello")
        await socket.close()

    return TestClient(OriginGuard(inner, ["http://localhost:5173", SITE]))


def test_only_irisclick_websites_may_use_the_desktop_app():
    c = guarded_app()
    assert c.post("/api/tracking/start").status_code == 200  # worker / launcher: no Origin
    assert c.post("/api/tracking/start", headers={"Origin": SITE}).status_code == 200
    assert c.post("/api/tracking/start", headers={"Origin": "http://localhost:5173"}).status_code == 200
    blocked = c.post("/api/tracking/start", headers={"Origin": EVIL})
    assert blocked.status_code == 403 and "not allowed" in blocked.json()["detail"]
    assert c.post("/api/tracking/start", headers={"Origin": "null"}).status_code == 403


def test_other_websites_cannot_open_the_calibration_websocket():
    c = guarded_app()
    with c.websocket_connect("/api/ws/calibration", headers={"Origin": SITE}) as ws:
        assert ws.receive_text() == "hello"
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/api/ws/calibration", headers={"Origin": EVIL}) as ws:
            ws.receive_text()


# --- Tokens ------------------------------------------------------------------------------------

@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setenv(desktop_tokens.SECRET_ENV, "s" * 40)


def test_tokens_carry_the_user_and_expire(secret):
    token, expires = desktop_tokens.make(LINK, 7, now=1000)
    assert expires == 1000 + 300
    assert desktop_tokens.read(token, LINK, now=1100) == 7
    with pytest.raises(TokenError):
        desktop_tokens.read(token, LINK, now=1300)       # expired
    with pytest.raises(TokenError):
        desktop_tokens.read(token, DESKTOP, now=1100)    # a link token is not a desktop token
    payload, signature = token.split(".")
    with pytest.raises(TokenError):
        desktop_tokens.read(f"{payload}.x{signature[1:]}", LINK, now=1100)  # tampered
    with pytest.raises(TokenError):
        desktop_tokens.read("garbage", LINK)


def test_without_a_secret_the_key_comes_from_the_database_password(monkeypatch):
    monkeypatch.delenv(desktop_tokens.SECRET_ENV, raising=False)
    with_password = get_settings().model_copy(update={"db_password": SecretStr("dummy-db-password")})
    monkeypatch.setattr(desktop_tokens, "get_settings", lambda: with_password)
    token, _ = desktop_tokens.make(DESKTOP, 3)
    assert desktop_tokens.read(token, DESKTOP) == 3
    no_password = get_settings().model_copy(update={"db_password": SecretStr("")})
    monkeypatch.setattr(desktop_tokens, "get_settings", lambda: no_password)
    with pytest.raises(TokenError):
        desktop_tokens.make(LINK, 3)


# --- Hosted server: link token → desktop session ------------------------------------------------

@pytest.fixture
def hosted(secret):
    from app.api.routes import assistive, auth
    app = FastAPI()
    for router in (cloud_desktop.me_router, cloud_desktop.desktop_router, assistive.router, auth.router):
        app.include_router(router, prefix="/api")
    with TestClient(app) as c:
        yield c


def test_signed_in_user_gets_a_link_token_that_buys_a_desktop_session(hosted, make_user):
    ana = make_user("Ana Cruz")
    assert hosted.post("/api/me/desktop-link").status_code == 401  # must be signed in
    assert hosted.post("/api/assistive/select", json={"user_id": ana}).status_code == 200
    link = hosted.post("/api/me/desktop-link").json()
    assert desktop_tokens.read(link["link_token"], LINK) == ana

    session = hosted.post("/api/desktop/session", json={"link_token": link["link_token"]})
    assert session.status_code == 200
    body = session.json()
    assert body["user"] == {"user_id": ana, "full_name": "Ana Cruz"}
    assert desktop_tokens.read(body["desktop_token"], DESKTOP) == ana
    # A desktop token cannot be used as a link token, and junk is refused.
    assert hosted.post("/api/desktop/session", json={"link_token": body["desktop_token"]}).status_code == 401
    assert hosted.post("/api/desktop/session", json={"link_token": "x" * 20}).status_code == 401


def test_a_deactivated_user_cannot_link(hosted, make_user):
    ana = make_user("Ana Cruz", status="inactive")
    token, _ = desktop_tokens.make(LINK, ana)
    assert hosted.post("/api/desktop/session", json={"link_token": token}).status_code == 401


# --- Desktop app: stores the link and sets the active user ---------------------------------------

@pytest.fixture
def desktop(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop_link, "session_path", tmp_path / "desktop_session.json")
    monkeypatch.setattr(desktop_link, "cloud_url", lambda: "https://iris-click.example.app")
    app = FastAPI()
    app.include_router(desktop_link.router, prefix="/api")
    return TestClient(app)


def test_desktop_links_to_the_user_and_makes_them_active(desktop, monkeypatch):
    calls = []

    def cloud(url, body):
        calls.append((url, body))
        return 200, {"desktop_token": "desk.tok", "expires_at": int(time.time()) + 3600,
                     "user": {"user_id": 42, "full_name": "Ana Cruz"}}

    monkeypatch.setattr(desktop_link, "post_json", cloud)
    assert desktop.get("/api/desktop/link").json() == {"connected_to_website": True, "linked": False, "user": None}
    linked = desktop.post("/api/desktop/link", json={"link_token": "link-token-123"}).json()
    assert calls == [("https://iris-click.example.app/api/desktop/session", {"link_token": "link-token-123"})]
    assert linked["linked"] is True and linked["user"]["full_name"] == "Ana Cruz"
    assert active_user.get_user_id() == 42
    assert desktop_link.load_session()["desktop_token"] == "desk.tok"

    assert desktop.post("/api/desktop/unlink").json()["linked"] is False
    assert active_user.get_user_id() is None and desktop_link.load_session() is None


def test_desktop_link_errors_are_clear(desktop, monkeypatch):
    monkeypatch.setattr(desktop_link, "post_json", lambda url, body: (401, {"detail": cloud_desktop.LINK_EXPIRED}))
    refused = desktop.post("/api/desktop/link", json={"link_token": "link-token-123"})
    assert refused.status_code == 401 and refused.json()["detail"] == cloud_desktop.LINK_EXPIRED

    def offline(url, body):
        raise OSError("no internet")

    monkeypatch.setattr(desktop_link, "post_json", offline)
    down = desktop.post("/api/desktop/link", json={"link_token": "link-token-123"})
    assert down.status_code == 502 and down.json()["detail"] == desktop_link.CANNOT_REACH
    assert active_user.get_user_id() is None


def test_today_s_local_setup_is_untouched_without_a_website_address(desktop, monkeypatch):
    monkeypatch.setattr(desktop_link, "cloud_url", lambda: "")
    response = desktop.post("/api/desktop/link", json={"link_token": "link-token-123"})
    assert response.status_code == 503 and response.json()["detail"] == desktop_link.NOT_SET_UP


def test_an_expired_saved_link_is_ignored(desktop):
    desktop_link._save_session({"desktop_token": "old", "expires_at": int(time.time()) - 1,
                                "user": {"user_id": 1, "full_name": "Old"}})
    assert desktop.get("/api/desktop/link").json()["linked"] is False


# --- Through the real apps (hooks in app/api/main.py, app/cloud/main.py, app/cloud/access.py) ---

def test_the_pc_server_blocks_other_websites_but_not_the_local_site(monkeypatch):
    from app.api import main
    settings = get_settings().model_copy(update={"cors_origins": ["http://localhost:5173", SITE]})
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    c = TestClient(main.create_app())
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/health", headers={"Origin": "http://localhost:5173"}).status_code == 200
    assert c.get("/api/health", headers={"Origin": SITE}).status_code == 200
    assert c.get("/api/health", headers={"Origin": EVIL}).status_code == 403
    assert c.get("/api/desktop/link").status_code == 200  # the link route is registered
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/api/ws/calibration", headers={"Origin": EVIL}) as ws:
            ws.receive_text()


def test_the_online_server_lets_only_the_desktop_session_past_the_access_code(monkeypatch, secret):
    from app.cloud import access
    from app.cloud import main as cloud
    monkeypatch.setenv(access.CODE_ENV, "test-access-code")
    with TestClient(cloud.create_app()) as c:
        # No access-code cookie: the desktop session path answers (refuses a bad token itself) ...
        assert c.post("/api/desktop/session", json={"link_token": "x" * 20}).status_code == 401
        # ... while everything else still needs the code first.
        assert c.post("/api/me/desktop-link").json()["code"] == "access_required"
