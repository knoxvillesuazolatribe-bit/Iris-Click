"""Online copy on Vercel (app/cloud, api/index.py): access code, PC-only parts, Vercel runtime."""

import os
import subprocess
import sys
import textwrap
from functools import lru_cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.pool import NullPool

from app.cloud import access
from app.cloud import main as cloud
from app.config import get_settings
from app.models import database
from app.services import neural_tts_service
from app.services.sos_dispatcher import dispatcher

from tests.auth.conftest import fresh_throttle, make_user  # noqa: F401  (fixtures)

CODE = "test-access-code"
REPO_DIR = Path(__file__).resolve().parents[3]


@pytest.fixture
def waits(monkeypatch):
    """Online copy with an access code set; wrong-code waits recorded, not slept."""
    seen = []
    monkeypatch.setenv(access.CODE_ENV, CODE)
    monkeypatch.setattr(access, "sleep", seen.append)
    monkeypatch.setattr(access, "wrong_codes", access._WrongCodes())
    return seen


def client():
    return TestClient(cloud.VercelPaths(cloud.create_app()), base_url="https://irisclick.example")


@pytest.fixture
def web(waits):
    with client() as c:
        yield c


@pytest.fixture
def unlocked(web):
    assert web.post("/api/cloud/access", json={"code": CODE}).status_code == 200
    return web


@pytest.fixture
def ana(unlocked, make_user):
    user_id = make_user("Ana Cruz")
    assert unlocked.post("/api/assistive/select", json={"user_id": user_id}).status_code == 200
    return unlocked


# --- Access code -----------------------------------------------------------------------------

def test_closed_until_an_access_code_is_set(monkeypatch):
    monkeypatch.delenv(access.CODE_ENV, raising=False)
    with client() as c:
        assert c.get("/api/cloud/status").json() == {"online_copy": True, "ready": False, "access": False}
        response = c.get("/api/assistive/users")
        assert response.status_code == 503 and response.json()["code"] == "not_set_up"
        assert c.post("/api/cloud/access", json={"code": "anything"}).status_code == 503


def test_a_short_code_does_not_open_it(monkeypatch):
    monkeypatch.setenv(access.CODE_ENV, "1234567")  # one short of MIN_CODE_LENGTH
    with client() as c:
        assert c.get("/api/cloud/status").json()["ready"] is False
        assert c.get("/api/assistive/users").status_code == 503


def test_everything_needs_the_code_first(web):
    assert web.get("/api/cloud/status").json() == {"online_copy": True, "ready": True, "access": False}
    for method, path in [("get", "/api/assistive/users"), ("post", "/api/auth/admin/login"),
                         ("get", "/api/me/sos"), ("post", "/api/tts/speak"),
                         ("get", "/api/health/database"), ("get", "/api/app-info")]:
        response = getattr(web, method)(path)
        assert response.status_code == 401, path
        assert response.json() == {"detail": access.ACCESS_REQUIRED, "code": "access_required"}
    assert web.get("/api/health").status_code == 200  # only the plain health check is open


def test_wrong_code_waits_and_right_code_opens(web, waits):
    response = web.post("/api/cloud/access", json={"code": "not-the-code"})
    assert response.status_code == 401 and response.json()["detail"] == access.WRONG_CODE
    assert waits == [access.WRONG_CODE_DELAY_S]
    assert access.COOKIE_NAME not in web.cookies

    response = web.post("/api/cloud/access", json={"code": f"  {CODE} "})
    assert response.status_code == 200 and response.json()["access"] is True
    assert web.get("/api/cloud/status").json()["access"] is True
    assert web.get("/api/assistive/users").status_code == 200


def test_the_cookie_is_not_the_code_and_is_secure(web):
    response = web.post("/api/cloud/access", json={"code": CODE})
    cookie = response.headers["set-cookie"]
    assert CODE not in cookie
    assert "HttpOnly" in cookie and "Secure" in cookie and "samesite=lax" in cookie.lower()


def test_changing_the_code_signs_every_device_out(unlocked, monkeypatch):
    monkeypatch.setenv(access.CODE_ENV, "a-brand-new-code")
    assert unlocked.get("/api/assistive/users").status_code == 401
    assert unlocked.get("/api/cloud/status").json()["access"] is False


def test_too_many_wrong_codes_pause_that_address(web):
    for _ in range(access.MAX_WRONG):
        assert web.post("/api/cloud/access", json={"code": "guess-guess"}).status_code == 401
    response = web.post("/api/cloud/access", json={"code": CODE})  # even the right one waits
    assert response.status_code == 429 and response.json()["detail"] == access.TOO_MANY
    other = {"x-real-ip": "203.0.113.9"}
    assert web.post("/api/cloud/access", json={"code": CODE}, headers=other).status_code == 200


# --- What the online copy serves -------------------------------------------------------------

def test_session_cookie_is_secure_on_https(unlocked, make_user):
    user_id = make_user("Ana Cruz")
    response = unlocked.post("/api/assistive/select", json={"user_id": user_id})
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]
    assert unlocked.get("/api/auth/me").status_code == 200


def test_home_and_tracking_view_work_without_a_tracker(ana):
    assert ana.get("/api/me/home").json()["full_name"] == "Ana Cruz"
    view = ana.get("/api/me/tracking")
    assert view.status_code == 200 and view.json()["state"] == "inactive"


@pytest.mark.parametrize("path", ["/api/me/tracking/start", "/api/me/tracking/stop",
                                  "/api/me/tracking/restart"])
def test_starting_tracking_says_pc_only(ana, path):
    response = ana.post(path)
    assert response.status_code == 409 and response.json()["detail"] == cloud.PC_ONLY_TRACKING


@pytest.mark.parametrize("path", ["/api/me/apps/notepad/launch", "/api/me/apps/tiles/1/launch"])
def test_opening_pc_apps_says_pc_only(ana, path):
    response = ana.post(path)
    assert response.status_code == 409 and response.json()["detail"] == cloud.PC_ONLY_APPS


def test_pc_only_answers_still_need_a_signed_in_user(unlocked):
    assert unlocked.post("/api/me/tracking/start").status_code == 401


def test_camera_calibration_and_worker_routes_are_not_online(unlocked):
    for path in ["/api/cameras", "/api/calibration-profiles", "/api/tracking/status"]:
        assert unlocked.get(path).status_code == 404, path
    for path in ["/docs", "/openapi.json", "/redoc"]:
        assert unlocked.get(path).status_code == 404, path


def test_voice_and_sos_work_online(ana):
    assert ana.get("/api/me/sos").status_code == 200
    assert ana.get("/api/me/voice").status_code == 200
    assert ana.get("/api/me/language").status_code == 200
    assert ana.get("/api/app-info").status_code == 200


def test_setup_check_needs_the_code_and_never_shows_values(web, monkeypatch):
    assert web.get("/api/cloud/check").status_code == 401
    assert web.post("/api/cloud/access", json={"code": CODE}).status_code == 200
    monkeypatch.setenv("DB_USER", "dummy-user")
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    report = web.get("/api/cloud/check").json()
    assert report["settings"]["IRISCLICK_ACCESS_CODE"] == "set"
    assert report["settings"]["DB_USER"] == "set" and report["settings"]["DB_PASSWORD"] == "missing"
    assert report["database"] == "ok" and report["error"] is None  # the test's SQLite database
    assert CODE not in str(report) and "dummy-user" not in str(report)


def test_setup_check_reports_the_database_reason_without_the_password(unlocked, monkeypatch):
    secret = "dummy-secret-123"
    with_password = get_settings().model_copy(update={"db_password": SecretStr(secret)})
    monkeypatch.setattr(cloud, "get_settings", lambda: with_password)

    def refuse():
        raise RuntimeError(f"password authentication failed (tried {secret})")

    monkeypatch.setattr(database, "check_connection", refuse)
    report = unlocked.get("/api/cloud/check").json()
    assert report["database"] == "error"
    assert report["error"].startswith("RuntimeError: password authentication failed")
    assert secret not in report["error"]


# --- Vercel runtime --------------------------------------------------------------------------

def test_rewritten_path_is_restored_and_other_query_kept(unlocked):
    response = unlocked.get("/api/index", params={cloud.PATH_PARAM: "cloud/status"})
    assert response.status_code == 200 and response.json()["access"] is True
    seen = {}

    async def echo(scope, receive, send):
        seen.update(path=scope["path"], query=scope["query_string"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    raw = TestClient(cloud.VercelPaths(echo))  # no "with": the echo app has no start-up
    raw.get("/api/index?__irisclick_path=admin/reports/sos&from=2026-01-01&to=2026-02-01")
    assert seen == {"path": "/api/admin/reports/sos", "query": b"from=2026-01-01&to=2026-02-01"}


def test_plain_http_cookies_are_left_alone(waits):
    with TestClient(cloud.VercelPaths(cloud.create_app()), base_url="http://localhost") as c:
        cookie = c.post("/api/cloud/access", json={"code": CODE}).headers["set-cookie"]
    assert "Secure" not in cookie


@pytest.fixture
def restore_runtime(monkeypatch):
    """configure_runtime changes process-wide settings; put them all back afterwards."""
    for name in cloud.STORAGE_SETTINGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(database, "get_engine", database.get_engine)
    monkeypatch.setattr(database, "get_session_factory", lru_cache(database.get_session_factory))
    monkeypatch.setattr(neural_tts_service, "cache_dir", neural_tts_service.cache_dir)
    monkeypatch.setattr(dispatcher, "inline", dispatcher.inline)
    monkeypatch.setattr(dispatcher, "delays", dispatcher.delays)
    yield
    get_settings.cache_clear()
    cloud.cloud_engine.cache_clear()


def test_runtime_writes_only_to_the_temp_folder_and_sends_sos_inline(tmp_path, restore_runtime):
    cloud.configure_runtime(tmp_path)
    settings = get_settings()
    for path in (settings.profiles_dir, settings.device_settings_path, settings.worker_pid_path,
                 settings.screenshots_dir, neural_tts_service.cache_dir):
        assert Path(path).is_relative_to(tmp_path)
    assert database.get_engine is cloud.cloud_engine
    assert dispatcher.inline is True and dispatcher.delays == cloud.SOS_RETRY_DELAYS_S
    assert sum(cloud.SOS_RETRY_DELAYS_S) < 60  # well inside the function's 120 s limit


def test_cloud_database_keeps_no_connections_open(monkeypatch):
    supabase = get_settings().model_copy(update={"db_host": "pooler.example", "db_port": 6543,
                                                 "db_user": "u"})
    monkeypatch.setattr(cloud, "get_settings", lambda: supabase)
    cloud.cloud_engine.cache_clear()
    try:
        engine = cloud.cloud_engine()
        assert isinstance(engine.pool, NullPool)
        assert engine.dialect.driver == "psycopg" and engine.url.port == 6543
    finally:
        cloud.cloud_engine.cache_clear()


def test_vercel_entry_loads_without_windows_or_camera_packages(tmp_path):
    """Vercel runs Linux: no ctypes.WinDLL, and no MediaPipe/OpenCV/numpy are installed."""
    script = textwrap.dedent(f"""
        import ctypes, importlib.util, sys
        for name in ("WinDLL", "windll", "OleDLL", "oledll"):
            if hasattr(ctypes, name):
                delattr(ctypes, name)
        BLOCKED = {{"cv2", "mediapipe", "numpy", "MNN", "pyautogui", "pyttsx3", "pystray",
                   "comtypes", "gazefollower", "winreg", "uvicorn", "alembic"}}
        class Blocker:
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in BLOCKED:
                    raise ImportError("not installed on Vercel: " + name)
        sys.meta_path.insert(0, Blocker())
        spec = importlib.util.spec_from_file_location("vercel_index", {str(REPO_DIR / "api" / "index.py")!r})
        index = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(index)
        from fastapi.testclient import TestClient
        with TestClient(index.app) as c:
            status = c.get("/api/index?__irisclick_path=cloud/status").json()
            assert status == {{"online_copy": True, "ready": True, "access": False}}, status
            assert c.get("/api/me/tracking").status_code == 401
        print("loaded")
    """)
    env = {**os.environ, "DB_HOST": "", "SQLITE_PATH": str(tmp_path / "x.db"),
           "IRISCLICK_STORAGE_DIR": str(tmp_path / "storage"), access.CODE_ENV: CODE}
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    assert "loaded" in result.stdout
