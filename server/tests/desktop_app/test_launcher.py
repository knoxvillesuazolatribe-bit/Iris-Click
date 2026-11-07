"""IrisClick Desktop launcher (app/launcher.py): start-up, hosted website, tray, sync, stop."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import pytest

from app import launcher

SITE = "https://iris-click.example.app"


def test_server_runs_with_console_python_beside_pythonw(tmp_path):
    (tmp_path / "pythonw.exe").write_bytes(b"")
    (tmp_path / "python.exe").write_bytes(b"")
    assert launcher.server_command(8000, tmp_path / "pythonw.exe") == [
        str(tmp_path / "python.exe"), "-m", "uvicorn", "app.api.main:app", "--host", "127.0.0.1", "--port", "8000"]


def test_the_hosted_website_may_use_the_desktop_app_and_its_pages_open_there(tmp_path):
    edge = tmp_path / "msedge.exe"
    env = launcher.server_env(8000, SITE, edge, ["http://localhost:5173"], base={"KEEP": "1"})
    assert json.loads(env["CORS_ORIGINS"]) == ["http://localhost:5173", SITE]
    assert env["SITE_URL"] == SITE and env["BROWSER"] == str(edge) and env["KEEP"] == "1"
    # already listed: not doubled; no Edge: no BROWSER
    env = launcher.server_env(8000, SITE, None, [SITE], base={})
    assert json.loads(env["CORS_ORIGINS"]) == [SITE] and "BROWSER" not in env


def test_finds_edge(tmp_path):
    present = tmp_path / "b" / "msedge.exe"
    present.parent.mkdir()
    present.write_bytes(b"")
    assert launcher.find_edge([tmp_path / "a" / "msedge.exe", present]) == present
    assert launcher.find_edge([tmp_path / "missing.exe"]) is None


def test_website_is_the_hosted_one_when_set_else_the_local_site(monkeypatch):
    from app.api.routes import desktop_link
    monkeypatch.setattr(desktop_link, "cloud_url", lambda: SITE)
    assert launcher.website_url() == SITE
    monkeypatch.setattr(desktop_link, "cloud_url", lambda: "")
    assert launcher.website_url().startswith("http://localhost")


def test_server_ready_checks_health():
    assert launcher.server_ready(8000, lambda url, timeout=2.0: (200, json.dumps({"status": "ok"})))
    assert not launcher.server_ready(8000, lambda url, timeout=2.0: (500, "{}"))

    def down(url, timeout=2.0):
        raise OSError("refused")

    assert not launcher.server_ready(8000, down)


def test_waiting_stops_when_ready_when_the_server_exits_or_at_the_timeout():
    clock = iter(range(1000)).__next__
    answers = iter([False, False, True])
    assert launcher.wait_until_ready(8000, ready=lambda p: next(answers), sleep=lambda s: None, clock=clock)

    class Exited:
        def poll(self):
            return 1

    assert not launcher.wait_until_ready(8000, Exited(), ready=lambda p: False, sleep=lambda s: None, clock=clock)
    assert not launcher.wait_until_ready(8000, timeout=3, ready=lambda p: False, sleep=lambda s: None, clock=clock)


def test_tracking_start_uses_the_newest_calibration_and_reports_none_yet():
    seen = []
    assert launcher.start_tracking(8000, lambda u, timeout=20.0: seen.append(u) or (200, '{"running": true}'))
    assert seen == ["http://127.0.0.1:8000/api/tracking/start"]
    assert launcher.start_tracking(8000, lambda u, timeout=20.0: (409, '{"detail":"Calibrate first."}')) is False


def test_the_window_opens_the_website_in_an_edge_app_window(tmp_path):
    opened = []
    launcher.open_window(SITE, tmp_path / "msedge.exe", popen=opened.append)
    assert opened == [[str(tmp_path / "msedge.exe"), f"--app={SITE}/", "--start-maximized"]]
    launcher.open_window(SITE, None, browser=opened.append)
    assert opened[-1] == f"{SITE}/"


class FakeRegistry:
    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, hive, path):
        return self._Key()

    CreateKey = OpenKey

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], 1

    def SetValueEx(self, key, name, _r, _t, value):
        self.values[name] = value

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


def test_start_with_windows_can_be_turned_on_and_off():
    reg = FakeRegistry()
    assert not launcher.starts_with_windows(reg)
    launcher.set_start_with_windows(True, reg)
    assert launcher.starts_with_windows(reg)
    assert reg.values[launcher.RUN_NAME].endswith('launch_irisclick.pyw"')
    launcher.set_start_with_windows(False, reg)
    launcher.set_start_with_windows(False, reg)  # already off: no error
    assert not launcher.starts_with_windows(reg)


def run_with(**fakes):
    calls = []
    defaults = dict(
        ready=lambda p: False, launch=lambda p, env: calls.append(("launch", env["SITE_URL"])) or object(),
        wait=lambda p, proc, tick: True, track=lambda p: True,
        show=lambda url, edge: calls.append(("window", url)), speak=lambda t: calls.append(t),
        retry=lambda m: calls.append(("retry", m)) or False,
        splash_factory=lambda: type("S", (), {"tick": lambda s: None, "close": lambda s: calls.append("splash closed")})(),
        sync_loop=lambda stop: calls.append("sync started"),
        tray_loop=lambda open_site, quit_all: calls.append("tray"),
        settings_cors=lambda: ["http://localhost:5173"],
    )
    defaults.update(fakes)
    return launcher.run(8000, **defaults), calls


@pytest.fixture
def hosted_site(monkeypatch):
    monkeypatch.setattr(launcher, "website_url", lambda: SITE)
    monkeypatch.setattr(launcher, "find_edge", lambda: None)


def test_start_up_opens_the_website_welcomes_and_keeps_the_tray_and_sync(hosted_site):
    code, calls = run_with()
    time.sleep(0.05)  # the sync thread
    assert code == 0
    assert calls[:4] == [("launch", SITE), "splash closed", ("window", SITE), launcher.WELCOME_TRACKING]
    assert "tray" in calls and "sync started" in calls


def test_without_a_calibration_the_welcome_asks_for_a_helper(hosted_site):
    code, calls = run_with(track=lambda p: False)
    assert code == 0 and launcher.WELCOME_NO_CALIBRATION in calls


def test_a_second_launch_only_opens_the_window(hosted_site):
    code, calls = run_with(ready=lambda p: True)
    assert code == 0 and calls == [("window", SITE), launcher.WELCOME_TRACKING]  # no server, tray or sync


def test_a_failed_start_is_spoken_and_offers_try_again(hosted_site):
    attempts = iter([False, True])
    code, calls = run_with(wait=lambda p, proc, tick: next(attempts), retry=lambda m: True)
    assert code == 0 and [c for c in calls if c[0:1] == ("launch",)].__len__() == 2
    assert launcher.START_FAILED in calls
    code, calls = run_with(wait=lambda p, proc, tick: False)
    assert code == 1 and ("retry", launcher.START_FAILED) in calls and ("window", SITE) not in calls


def test_quit_from_the_tray_stops_sync_tracking_and_the_server(monkeypatch, hosted_site):
    stopped, sync_stop = [], {}
    monkeypatch.setattr(launcher, "stop", lambda port: stopped.append(port))

    def sync_loop(stop_event):
        sync_stop["event"] = stop_event

    def tray(open_site, quit_all):
        time.sleep(0.05)
        quit_all()

    code, _ = run_with(sync_loop=sync_loop, tray_loop=tray)
    assert code == 0 and stopped == [8000] and sync_stop["event"].is_set()


def test_stop_ends_tracking_then_the_server(tmp_path):
    (tmp_path / launcher.SERVER_PID).write_text("4321", encoding="utf-8")
    posted, killed = [], []
    launcher.stop(8000, tmp_path, post=lambda u, timeout=20.0: posted.append(u) or (200, "{}"), kill=killed.append)
    assert posted == ["http://127.0.0.1:8000/api/tracking/stop"] and killed == [4321]
    assert not (tmp_path / launcher.SERVER_PID).exists()


def test_stop_also_ends_the_tray_launcher(tmp_path):
    (tmp_path / launcher.SERVER_PID).write_text("4321", encoding="utf-8")
    (tmp_path / launcher.LAUNCHER_PID).write_text("8765", encoding="utf-8")
    killed = []
    launcher.stop(8000, tmp_path, post=lambda u, timeout=20.0: (200, "{}"), kill=killed.append)
    assert killed == [4321, 8765] and not (tmp_path / launcher.LAUNCHER_PID).exists()


def test_tray_icon_image_is_drawn():
    assert launcher.tray_image(32).size == (32, 32)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(sys.platform != "win32", reason="IrisClick Desktop is Windows-only")
def test_real_server_starts_hidden_lets_the_website_in_and_stops(tmp_path):
    """Starts the real server the way the shortcut does, on a spare port."""
    port = free_port()
    env = launcher.server_env(port, SITE, None, ["http://localhost:5173"])
    env.update(DB_HOST="", SQLITE_PATH=str(tmp_path / "test.db"))
    storage = tmp_path / "storage"
    process = launcher.start_server(port, env, storage)
    try:
        assert launcher.wait_until_ready(port, process, timeout=60)
        allowed = urllib.request.Request(f"http://127.0.0.1:{port}/api/health", headers={"Origin": SITE})
        with urllib.request.urlopen(allowed, timeout=5) as answer:
            assert answer.status == 200
        blocked = urllib.request.Request(f"http://127.0.0.1:{port}/api/health",
                                         headers={"Origin": "https://evil.example.com"})
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(blocked, timeout=5)
        assert refused.value.code == 403
    finally:
        launcher.stop(port, storage)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
    time.sleep(0.5)
    assert not launcher.server_ready(port)
    assert os.environ.get("SITE_URL") != SITE  # only the child process got it
