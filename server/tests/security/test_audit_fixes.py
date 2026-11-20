"""Security and safety audit (Nov 2026): one test per gap that was found and fixed."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.accounts import mode, sms, sms_codes
from app.api.origin_guard import OriginGuard, host_name
from app.cloud import access
from app.cloud import main as cloud
from app.services import auth_service
from app.services.user_apps_service import UserAppsError, clean_url
from app.workers.paused_resume import RESUME_HINT, PausedResume
from tests.accounts.test_forgot_pin_sms import (api as accounts_api, own_file,  # noqa: F401
                                                signing_secret, texts)
from tests.auth.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, admin_id, api  # noqa: F401

SITE = "https://irisclick.vercel.app"


# --- Desktop: DNS rebinding ----------------------------------------------------------------

def guarded(base_url: str) -> TestClient:
    app = FastAPI()
    app.get("/api/desktop/device")(lambda: {"device_id": "secret-computer-id"})
    app.add_middleware(OriginGuard, allowed=[SITE])
    return TestClient(app, base_url=base_url)


@pytest.mark.parametrize("base_url", ["http://127.0.0.1:8000", "http://localhost:8000", "http://[::1]:8000"])
def test_the_desktop_answers_requests_addressed_to_this_computer(base_url):
    assert guarded(base_url).get("/api/desktop/device").status_code == 200
    assert guarded(base_url).get("/api/desktop/device", headers={"Origin": SITE}).status_code == 200


@pytest.mark.parametrize("base_url", ["http://rebind.attacker.example:8000", "http://127.0.0.1.nip.io:8000"])
def test_a_rebinding_website_cannot_read_the_desktop_without_an_origin(base_url):
    """A site that points its own name at 127.0.0.1 sends same-origin GETs with no Origin."""
    answer = guarded(base_url).get("/api/desktop/device")
    assert answer.status_code == 403 and "secret-computer-id" not in answer.text


def test_other_websites_are_still_refused():
    assert guarded("http://127.0.0.1:8000").get("/api/desktop/device",
                                                headers={"Origin": "https://evil.example"}).status_code == 403


def test_host_names():
    assert host_name("127.0.0.1:8000") == "127.0.0.1" and host_name("[::1]:8000") == "::1"
    assert host_name("LOCALHOST") == "localhost" and host_name("evil.example:8000") == "evil.example"


# --- Edit Apps: website links --------------------------------------------------------------

@pytest.mark.parametrize("link", [
    "javascript:alert(1)", "JaVaScRiPt:alert(1)", " javascript:alert(1)", "data:text/html,<script>x</script>",
    "vbscript:msgbox(1)", "file:///C:/Windows/System32/calc.exe", "ms-settings:privacy",
    'http://evil.example"><script>alert(1)</script>', "https://bank.example@evil.example",
    "https://user:pass@evil.example", "https://evil.example/" + chr(92) + "x", "https://a.example/{x}",
])
def test_unsafe_links_are_refused(link):
    with pytest.raises(UserAppsError):
        clean_url(link)


@pytest.mark.parametrize(("link", "kept"), [
    ("youtube.com", "https://youtube.com"),
    ("https://www.google.com/search?q=irisclick&hl=fil#top", "https://www.google.com/search?q=irisclick&hl=fil#top"),
])
def test_normal_links_still_work(link, kept):
    assert clean_url(link) == kept


# --- SMS credits ----------------------------------------------------------------------------

def numbers(count):
    return [f"0917 {n:03d} {n:04d}" for n in range(100, 100 + count)]


def test_one_computer_cannot_text_codes_to_many_numbers(accounts_api, texts, monkeypatch):  # noqa: F811
    monkeypatch.setenv(sms.ONLY_TO_ENV, "")
    device = {"X-IrisClick-Device": "D" * 43}
    answers = [accounts_api.post("/api/accounts/mobile/send", json={"mobile_number": n}, headers=device)
               for n in numbers(sms_codes.TEXTS_PER_HOUR_PER_DEVICE + 2)]
    assert [a.status_code for a in answers].count(200) == sms_codes.TEXTS_PER_HOUR_PER_DEVICE
    assert answers[-1].status_code == 429 and answers[-1].json()["code"] == "sms_limit"
    assert len(texts) == sms_codes.TEXTS_PER_HOUR_PER_DEVICE


def test_the_whole_site_has_an_hourly_text_limit(accounts_api, texts, monkeypatch):  # noqa: F811
    """New made-up computer IDs every time still hit the site-wide cap."""
    monkeypatch.setenv(sms.ONLY_TO_ENV, "")
    monkeypatch.setattr(sms_codes, "TEXTS_PER_HOUR_SITE", 4)
    answers = [accounts_api.post("/api/accounts/mobile/send", json={"mobile_number": n},
                                 headers={"X-IrisClick-Device": chr(65 + i) * 43})
               for i, n in enumerate(numbers(6))]
    assert [a.status_code for a in answers] == [200] * 4 + [429] * 2
    assert len(texts) == 4


# --- Admin password lockout on Vercel ------------------------------------------------------

def test_the_admin_lockout_survives_a_fresh_server_copy(api, admin_id, monkeypatch):  # noqa: F811
    for _ in range(auth_service.MAX_FAILURES):
        assert api.post("/api/auth/admin/login", json={"email": ADMIN_EMAIL, "password": "wrong"}).status_code == 401
    # A new Vercel copy: its in-memory throttle knows nothing; the database still does.
    monkeypatch.setattr(auth_service, "throttle", auth_service.LoginThrottle())
    blocked = api.post("/api/auth/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert blocked.status_code == 429


def test_a_few_wrong_passwords_do_not_lock_out(api, admin_id):  # noqa: F811
    for _ in range(auth_service.MAX_FAILURES - 1):
        api.post("/api/auth/admin/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert api.post("/api/auth/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).status_code == 200


# --- Cookies, database host and the setup check online --------------------------------------

def test_the_sign_in_cookie_is_secure_online(api, admin_id, monkeypatch):  # noqa: F811
    monkeypatch.setenv("VERCEL", "1")
    answer = api.post("/api/auth/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    cookie = answer.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_the_pc_cookie_works_over_plain_http(api, admin_id, monkeypatch):  # noqa: F811
    monkeypatch.delenv("VERCEL", raising=False)
    answer = api.post("/api/auth/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert "secure" not in answer.headers["set-cookie"].lower()


def test_the_database_host_is_never_shown_online(api, monkeypatch):  # noqa: F811
    monkeypatch.setenv("VERCEL", "1")
    assert api.get("/api/health/database").json()["host"] is None


def test_the_open_website_shows_only_build_and_database_state(monkeypatch):
    """The live site: accounts sign-in on, no access code."""
    monkeypatch.delenv(access.CODE_ENV, raising=False)
    monkeypatch.setenv(mode.ENV_NAME, "device_accounts")
    with TestClient(cloud.VercelPaths(cloud.create_app()), base_url="https://irisclick.example") as web:
        report = web.get("/api/cloud/check").json()
    assert set(report) == {"build", "database"}


# --- Eye tracking: never trapped in "Paused" -----------------------------------------------

def test_two_both_eye_blinks_resume():
    resume = PausedResume(window_s=1.8)
    assert resume.both_blink(10.0) is False
    assert resume.both_blink(11.0) is True


def test_one_blink_or_slow_blinks_do_not_resume():
    resume = PausedResume(window_s=1.8)
    assert resume.both_blink(10.0) is False
    assert resume.both_blink(13.0) is False  # too slow: this is a new first blink
    resume.reset()
    assert resume.both_blink(13.5) is False


def test_the_pause_message_says_how_to_resume_hands_free():
    assert "Blink both eyes twice" in RESUME_HINT
