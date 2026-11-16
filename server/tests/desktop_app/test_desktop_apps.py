"""Adviser: apps open from the hosted website through IrisClick Desktop; the keyboard is an app tile."""

import queue
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routes import desktop_apps
from app.services import apps_service, user_apps_service
from app.services.apps_service import AppError
from app.workers import keyboard_request
from app.workers.tracking_worker import TrackingWorker

START_MENU = r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"
NOTEPAD = rf"{START_MENU}\Notepad.lnk"


class FakeDb:
    def commit(self):
        pass


@pytest.fixture
def pc(monkeypatch):
    """A linked person, one Start-menu program, and a recording opener."""
    opened, logged = [], []
    monkeypatch.setattr(desktop_apps, "linked_user", lambda db: SimpleNamespace(user_id=7, full_name="Ana"))
    monkeypatch.setattr(desktop_apps, "log_activity", lambda *a, **k: logged.append(a[1]))
    monkeypatch.setattr(user_apps_service, "scanner",
                        lambda: [user_apps_service.InstalledApp("Notepad", NOTEPAD)])
    monkeypatch.setattr(user_apps_service, "file_exists", lambda path: True)
    monkeypatch.setattr(apps_service, "opener", opened.append)
    monkeypatch.setitem(apps_service.finder, "calculator", lambda: r"C:\Windows\System32\calc.exe")
    return SimpleNamespace(opened=opened, logged=logged)


def _open(**body):
    return desktop_apps.open_app(desktop_apps.OpenRequest(**body), db=FakeDb())


def test_a_start_menu_program_opens_on_this_pc(pc):
    assert _open(kind="installed_app", path=NOTEPAD) == {"launched": True, "label": "Notepad"}
    assert pc.opened == [NOTEPAD] and pc.logged == ["Ana opened Notepad"]


def test_a_built_in_app_opens_on_this_pc(pc):
    assert _open(kind="builtin", key="calculator")["label"] == "Calculator"
    assert pc.opened == [r"C:\Windows\System32\calc.exe"]


@pytest.mark.parametrize(("path", "status"), [
    (rf"{START_MENU}\Other.lnk", 404),        # not in this PC's Start-menu scan
    (r"C:\Windows\System32\cmd.exe", 404),    # an .exe, but not a Start-menu program
    (rf"{START_MENU}\notes.txt", 422),        # not a program at all
])
def test_paths_outside_the_start_menu_scan_are_refused(pc, path, status):
    with pytest.raises(HTTPException) as refused:
        _open(kind="installed_app", path=path)
    assert refused.value.status_code == status and pc.opened == []


def test_an_unknown_built_in_app_is_refused(pc):
    with pytest.raises(HTTPException) as refused:
        _open(kind="builtin", key="powershell")
    assert refused.value.status_code == 404 and pc.opened == []


def test_nobody_linked_opens_nothing(monkeypatch):
    from app.api.routes import desktop_link
    monkeypatch.setattr(desktop_link, "load_session", lambda: None)
    opened = []
    monkeypatch.setattr(apps_service, "opener", opened.append)
    with pytest.raises(HTTPException) as refused:
        _open(kind="builtin", key="calculator")
    assert refused.value.status_code == 409 and opened == []


def test_other_websites_cannot_open_apps():
    from app.api.main import create_app
    client = TestClient(create_app())
    response = client.post("/api/desktop/apps/open", json={"kind": "builtin", "key": "calculator"},
                           headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_online_copy_stores_start_menu_programs_and_trusts_the_pc():
    from app.cloud import main as cloud
    cloud.assume_pc_apps()  # tests/conftest.py restores the real checks afterwards
    found = user_apps_service._scanned(NOTEPAD)
    assert found is not None and found.name == "Notepad"
    assert user_apps_service._scanned(r"C:\Windows\System32\cmd.exe") is None  # not Start menu
    assert user_apps_service._scanned(rf"{START_MENU}\notes.txt") is None  # not a program
    assert user_apps_service.file_exists(NOTEPAD) is True


# --- On-Screen Keyboard tile ------------------------------------------------------------------

@pytest.fixture
def worker_settings(tmp_path):
    return SimpleNamespace(worker_pid_path=tmp_path / "tracking_worker.pid")


def test_keyboard_is_a_built_in_tile_but_not_a_phase_9_shortcut():
    assert "keyboard" in [a.app_id for a in apps_service.builtins()]
    assert "keyboard" not in [a.app_id for a in apps_service.available()]


def test_keyboard_needs_eye_tracking(worker_settings):
    with pytest.raises(AppError) as refused:
        keyboard_request.ask(worker_settings, running=False)
    assert refused.value.status_code == 409
    assert keyboard_request.take(worker_settings) is False


def test_keyboard_request_is_taken_once(worker_settings):
    keyboard_request.ask(worker_settings, running=True)
    assert keyboard_request.take(worker_settings) is True
    assert keyboard_request.take(worker_settings) is False


def test_worker_toggles_the_keyboard_for_the_tile(worker_settings):
    toggled = []
    keyboard_request.ask(worker_settings, running=True)
    host = SimpleNamespace(commands=queue.Queue(), settings=worker_settings,
                           _extras=SimpleNamespace(toggle_keyboard=lambda: toggled.append(1)))
    TrackingWorker._handle_commands(host)
    TrackingWorker._handle_commands(host)  # the request is used once
    assert toggled == [1]


def test_opening_the_keyboard_tile_asks_the_worker(monkeypatch):
    asked = []
    monkeypatch.setattr(keyboard_request, "ask", lambda: asked.append(1))
    opened = []
    monkeypatch.setattr(apps_service, "opener", opened.append)
    assert apps_service.launch("keyboard").label == "On-Screen Keyboard"
    assert asked == [1] and opened == []
