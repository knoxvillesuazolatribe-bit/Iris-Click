"""Customizable Apps tiles (extension): defaults, add/remove/move/reset, safety."""

import pytest
from sqlalchemy import select

from app.models.user_app_shortcut import UserAppShortcut
from app.services import user_apps_service
from app.services.user_apps_service import InstalledApp

from tests.home.test_apps_routes import machine  # noqa: F401  (fixture)
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

NOTEPAD = r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Accessories\Notepad.lnk"
PAINT = r"C:\Users\ana\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Paint.lnk"


@pytest.fixture
def start_menu(monkeypatch, machine):
    """A fake Start Menu; ``files`` are the shortcuts that exist on disk."""
    state = {"apps": [InstalledApp("Notepad", NOTEPAD), InstalledApp("Paint", PAINT)],
             "files": {NOTEPAD, PAINT}}
    monkeypatch.setattr(user_apps_service, "scanner", lambda: list(state["apps"]))
    monkeypatch.setattr(user_apps_service, "file_exists", lambda path: path in state["files"])
    return state


def select_user(api, user_id):
    assert api.post("/api/assistive/select", json={"user_id": user_id}).status_code == 200


@pytest.fixture
def ana(api, make_user, start_menu):
    user_id = make_user("Ana Cruz")
    select_user(api, user_id)
    return user_id


def tiles(api):
    return api.get("/api/me/apps/tiles").json()


def labels(api):
    return [t["label"] for t in tiles(api)["tiles"]]


def tile_id(api, label):
    return next(t["tile_id"] for t in tiles(api)["tiles"] if t["label"] == label)


def add_site(api, label, url):
    return api.post("/api/me/apps/tiles", json={"kind": "website", "label": label, "url": url})


# --- Defaults --------------------------------------------------------------------------------

def test_first_load_gives_the_phase_9_defaults_once(api, ana, test_database):
    # Only Word of the Office apps is installed on the fake computer (Phase 9 rule kept).
    assert labels(api) == ["Browser", "Calculator", "Calendar (website)", "Word"]
    body = tiles(api)
    calendar = body["tiles"][2]
    assert "internet" in calendar["note"] and body["max_tiles"] == 12
    assert len(logs(test_database, "app_tiles_created")) == 1
    with test_database() as session:
        rows = session.scalars(select(UserAppShortcut)).all()
    assert [r.builtin_key for r in rows] == ["browser", "calculator", "calendar", "word", "excel", "powerpoint"]


def test_default_tiles_still_launch_through_phase_9(api, ana, machine, test_database):
    body = api.post(f"/api/me/apps/tiles/{tile_id(api, 'Word')}/launch").json()
    assert body == {"launched": True, "label": "Word"}
    assert machine["opened"] == [r"C:\Office\WINWORD.EXE"]
    assert [l.activity_description for l in logs(test_database, "app_launched")] == ["Ana Cruz opened Word"]


def test_old_phase_9_endpoints_are_unchanged(api, ana):
    assert [a["app_id"] for a in api.get("/api/me/apps").json()] == ["browser", "calculator", "calendar", "word"]


# --- Remove, add back, move, reset ------------------------------------------------------------

def test_removing_a_default_hides_it_and_it_can_come_back(api, ana, test_database):
    word = tile_id(api, "Word")
    assert api.delete(f"/api/me/apps/tiles/{word}").status_code == 204
    body = tiles(api)
    assert "Word" not in [t["label"] for t in body["tiles"]]
    assert [h["label"] for h in body["hidden_defaults"]] == ["Word"]
    assert api.post(f"/api/me/apps/tiles/{word}/launch").status_code == 404
    response = api.post("/api/me/apps/tiles", json={"kind": "builtin", "builtin_key": "word"})
    assert response.status_code == 201 and labels(api)[-1] == "Word"
    assert len(logs(test_database, "app_tile_removed")) == 1
    assert len(logs(test_database, "app_tile_restored")) == 1


def test_a_default_missing_on_this_computer_cannot_be_added(api, ana):
    response = api.post("/api/me/apps/tiles", json={"kind": "builtin", "builtin_key": "excel"})
    assert response.status_code == 404


def test_move_puts_a_tile_where_asked(api, ana, test_database):
    response = api.patch(f"/api/me/apps/tiles/{tile_id(api, 'Word')}", json={"position": 0})
    assert [t["label"] for t in response.json()["tiles"]] == ["Word", "Browser", "Calculator", "Calendar (website)"]
    api.patch(f"/api/me/apps/tiles/{tile_id(api, 'Word')}", json={"position": 99})
    assert labels(api)[-1] == "Word"
    assert len(logs(test_database, "app_tile_reordered")) == 2


def test_reset_restores_the_defaults_and_drops_added_apps(api, ana, test_database):
    add_site(api, "YouTube", "youtube.com")
    api.delete(f"/api/me/apps/tiles/{tile_id(api, 'Browser')}")
    api.patch(f"/api/me/apps/tiles/{tile_id(api, 'Word')}", json={"position": 0})
    body = api.post("/api/me/apps/tiles/reset").json()
    assert [t["label"] for t in body["tiles"]] == ["Browser", "Calculator", "Calendar (website)", "Word"]
    assert body["hidden_defaults"] == []
    assert len(logs(test_database, "app_tiles_reset")) == 1


# --- Websites ---------------------------------------------------------------------------------

def test_add_and_open_a_website(api, ana, machine, test_database):
    response = add_site(api, "YouTube", "youtube.com")
    assert response.status_code == 201
    tile = response.json()["tiles"][-1]
    assert tile["label"] == "YouTube" and tile["icon"] == "video" and tile["kind"] == "website"
    api.post(f"/api/me/apps/tiles/{tile['tile_id']}/launch")
    assert machine["opened"] == ["https://youtube.com"]
    assert [l.activity_description for l in logs(test_database, "app_tile_added")] == [
        "YouTube added to the apps of Ana Cruz"]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///C:/Windows/System32/cmd.exe",
                                 "data:text/html,hello", "ftp://example.com", "", "not a site",
                                 "localhost:8000", "https://" + "a" * 2050 + ".com"])
def test_unsafe_or_broken_website_addresses_are_refused(api, ana, url, test_database):
    assert add_site(api, "Bad", url).status_code == 422
    assert "Bad" not in labels(api)
    assert logs(test_database, "app_tile_added") == []


def test_same_website_twice_is_refused(api, ana):
    add_site(api, "Google", "https://www.google.com")
    response = add_site(api, "Search", "HTTPS://WWW.GOOGLE.COM")
    assert response.status_code == 409 and "already" in response.json()["detail"]


def test_long_names_are_shortened(api, ana):
    add_site(api, "A" * 120, "https://example.com")
    assert labels(api)[-1] == "A" * 40


def test_twelve_tiles_at_most(api, ana):
    for n in range(8):  # 4 defaults shown + 8 = 12
        assert add_site(api, f"Site {n}", f"https://site{n}.example.com").status_code == 201
    response = add_site(api, "One too many", "https://more.example.com")
    assert response.status_code == 409 and "12" in response.json()["detail"]


# --- Installed apps ----------------------------------------------------------------------------

def test_start_menu_apps_are_listed_and_can_be_added(api, ana, machine):
    assert api.get("/api/me/apps/available").json() == [
        {"name": "Notepad", "path": NOTEPAD}, {"name": "Paint", "path": PAINT}]
    response = api.post("/api/me/apps/tiles", json={"kind": "installed_app", "path": NOTEPAD.lower()})
    assert response.status_code == 201
    tile = response.json()["tiles"][-1]
    assert tile["label"] == "Notepad" and tile["available"] is True
    api.post(f"/api/me/apps/tiles/{tile['tile_id']}/launch")
    assert machine["opened"] == [NOTEPAD]


@pytest.mark.parametrize("path", [r"C:\Windows\System32\cmd.exe", r"C:\Users\ana\evil.bat",
                                  r"C:\temp\run.ps1", r"C:\temp\setup.msi", "notepad"])
def test_only_start_menu_shortcuts_can_be_added(api, ana, path):
    response = api.post("/api/me/apps/tiles", json={"kind": "installed_app", "path": path})
    assert response.status_code == 422
    assert len(labels(api)) == 4


def test_uninstalled_app_says_so_and_never_opens(api, ana, machine, start_menu):
    api.post("/api/me/apps/tiles", json={"kind": "installed_app", "path": PAINT})
    start_menu["apps"] = [InstalledApp("Notepad", NOTEPAD)]
    start_menu["files"] = {NOTEPAD}
    tile = tiles(api)["tiles"][-1]
    assert tile["available"] is False and tile["problem"] == "Paint isn't installed on this computer."
    response = api.post(f"/api/me/apps/tiles/{tile['tile_id']}/launch")
    assert response.status_code == 404 and "isn't installed" in response.json()["detail"]
    assert machine["opened"] == []
    assert api.delete(f"/api/me/apps/tiles/{tile['tile_id']}").status_code == 204


def test_failed_launch_says_so_and_is_not_logged(api, ana, machine, test_database):
    add_site(api, "Gmail", "https://mail.google.com")
    machine["fail"] = True
    response = api.post(f"/api/me/apps/tiles/{tile_id(api, 'Gmail')}/launch")
    assert response.status_code == 500 and "could not be opened" in response.json()["detail"]
    assert logs(test_database, "app_launched") == []


def test_scan_finding_nothing_is_an_empty_list(api, ana, start_menu):
    start_menu["apps"] = []
    assert api.get("/api/me/apps/available").json() == []


# --- Launch by id only, per user ---------------------------------------------------------------

def test_launch_ignores_anything_the_request_sends(api, ana, machine):
    add_site(api, "Google", "https://www.google.com")
    api.post(f"/api/me/apps/tiles/{tile_id(api, 'Google')}/launch",
             json={"target": r"C:\Windows\System32\cmd.exe", "path": "cmd.exe"})
    assert machine["opened"] == ["https://www.google.com"]


def test_a_tile_changed_in_the_database_is_checked_again_at_launch(api, ana, machine, test_database):
    add_site(api, "Google", "https://www.google.com")
    google = tile_id(api, "Google")
    with test_database() as session:
        session.get(UserAppShortcut, google).target = "file:///C:/Windows/System32/cmd.exe"
        session.commit()
    assert api.post(f"/api/me/apps/tiles/{google}/launch").status_code == 422
    assert machine["opened"] == []


def test_users_only_reach_their_own_tiles(api, ana, make_user, machine):
    add_site(api, "Ana's site", "https://ana.example.com")
    anas = tile_id(api, "Ana's site")
    select_user(api, make_user("Ben Reyes"))
    assert "Ana's site" not in labels(api)
    assert api.post(f"/api/me/apps/tiles/{anas}/launch").status_code == 404
    assert api.delete(f"/api/me/apps/tiles/{anas}").status_code == 404
    assert api.patch(f"/api/me/apps/tiles/{anas}", json={"position": 0}).status_code == 404
    assert machine["opened"] == []


def test_only_assistive_users(api, signed_in_admin, start_menu):
    assert signed_in_admin.get("/api/me/apps/tiles").status_code == 403
    assert signed_in_admin.get("/api/me/apps/available").status_code == 403
    signed_in_admin.post("/api/auth/logout")
    assert api.get("/api/me/apps/tiles").status_code == 401


# --- Admin --------------------------------------------------------------------------------------

def test_admin_can_view_and_edit_a_users_apps(signed_in_admin, make_user, start_menu, test_database):
    ana = make_user("Ana Cruz")
    base = f"/api/admin/users/{ana}/apps"
    assert [t["label"] for t in signed_in_admin.get(base).json()["tiles"]] == [
        "Browser", "Calculator", "Calendar (website)", "Word"]
    body = signed_in_admin.post(base, json={"kind": "website", "label": "Facebook",
                                            "url": "https://facebook.com"}).json()
    facebook = body["tiles"][-1]["tile_id"]
    assert signed_in_admin.patch(f"{base}/{facebook}", json={"position": 0}).json()["tiles"][0]["label"] == "Facebook"
    assert signed_in_admin.delete(f"{base}/{facebook}").status_code == 204
    assert signed_in_admin.get(f"{base}/available").json()[0]["name"] == "Notepad"
    assert signed_in_admin.post(f"{base}/reset").status_code == 200
    added = logs(test_database, "app_tile_added")[0].activity_description
    assert added.startswith("Facebook added to the apps of Ana Cruz by ")


def test_admin_apps_need_an_assistive_user_and_an_admin(api, signed_in_admin, admin_id, make_user,
                                                        start_menu):
    assert signed_in_admin.get(f"/api/admin/users/{admin_id}/apps").status_code == 404
    assert signed_in_admin.get("/api/admin/users/9999/apps").status_code == 404
    ana = make_user("Ana Cruz")
    select_user(api, ana)
    assert api.get(f"/api/admin/users/{ana}/apps").status_code == 403
