"""App shortcuts (Phase 9): a fixed list, only installed apps, logged launches."""

import pytest

from app.services import apps_service

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


@pytest.fixture
def machine(monkeypatch):
    """A fake computer: what is installed, and what was opened."""
    state = {"apps": {"WINWORD.EXE": r"C:\Office\WINWORD.EXE"}, "protocols": set(),
             "calc": r"C:\Windows\System32\calc.exe", "opened": [], "fail": False}
    monkeypatch.setitem(apps_service.finder, "app_path", lambda exe: state["apps"].get(exe))
    monkeypatch.setitem(apps_service.finder, "has_protocol", lambda p: p in state["protocols"])
    monkeypatch.setitem(apps_service.finder, "calculator", lambda: state["calc"])

    def opener(target):
        if state["fail"]:
            raise OSError("blocked")
        state["opened"].append(target)

    monkeypatch.setattr(apps_service, "opener", opener)
    return state


@pytest.fixture
def ana(api, make_user, machine):
    user_id = make_user("Ana Cruz")
    assert api.post("/api/assistive/select", json={"user_id": user_id}).status_code == 200
    return user_id


def test_only_installed_apps_are_listed(api, ana, machine):
    apps = {a["app_id"]: a for a in api.get("/api/me/apps").json()}
    assert list(apps) == ["browser", "calculator", "calendar", "word"]
    assert apps["calendar"]["label"] == "Calendar (website)"
    assert "internet" in apps["calendar"]["note"]
    machine["calc"] = None
    machine["protocols"].add("outlookcal")
    apps = {a["app_id"]: a for a in api.get("/api/me/apps").json()}
    assert "calculator" not in apps and apps["calendar"]["label"] == "Calendar"


def test_launch_opens_the_fixed_target_and_logs(api, ana, machine, test_database):
    body = api.post("/api/me/apps/word/launch").json()
    assert body == {"launched": True, "label": "Word"}
    assert machine["opened"] == [r"C:\Office\WINWORD.EXE"]
    api.post("/api/me/apps/calendar/launch")
    assert machine["opened"][-1] == apps_service.GOOGLE_CALENDAR
    assert [l.activity_description for l in logs(test_database, "app_launched")] == [
        "Ana Cruz opened Word", "Ana Cruz opened Calendar (website)"]


@pytest.mark.parametrize("app_id", ["excel", "notepad", "..%2F..%2Fcmd", "cmd.exe"])
def test_unknown_or_missing_apps_are_refused(api, ana, machine, app_id):
    assert api.post(f"/api/me/apps/{app_id}/launch").status_code == 404
    assert machine["opened"] == []


def test_failed_launch_says_so(api, ana, machine, test_database):
    machine["fail"] = True
    response = api.post("/api/me/apps/word/launch")
    assert response.status_code == 500
    assert "could not be opened" in response.json()["detail"]
    assert logs(test_database, "app_launched") == []


def test_only_assistive_users(api, signed_in_admin, machine):
    assert signed_in_admin.get("/api/me/apps").status_code == 403
    assert signed_in_admin.post("/api/me/apps/word/launch").status_code == 403
    signed_in_admin.post("/api/auth/logout")
    assert api.get("/api/me/apps").status_code == 401
