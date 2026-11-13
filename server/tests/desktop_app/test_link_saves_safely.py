"""Two links at the same moment must not fail (found in testing: 500 "Access is denied" on Windows)."""

import threading

import pytest

from app.api.routes import desktop_link


@pytest.fixture
def session_file(tmp_path, monkeypatch):
    path = tmp_path / "desktop_session.json"
    monkeypatch.setattr(desktop_link, "session_path", path)
    return path


def test_many_saves_at_once_all_succeed_and_leave_no_temporary_files(session_file):
    errors = []

    def save(n):
        try:
            desktop_link._save_session({"user": {"user_id": n}, "expires_at": 9e12, "desktop_token": "t"})
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=save, args=(n,)) for n in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert desktop_link.load_session()["user"]["user_id"] in range(20)
    assert list(session_file.parent.glob("*.tmp")) == []


def test_a_busy_file_is_retried(session_file, monkeypatch):
    real_replace = type(session_file).replace
    calls = []

    def flaky(self, target):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("in use")
        return real_replace(self, target)

    monkeypatch.setattr(type(session_file), "replace", flaky)
    desktop_link._save_session({"expires_at": 9e12, "user": {"user_id": 1}, "desktop_token": "t"})
    assert len(calls) == 3 and desktop_link.load_session() is not None


def test_unlinking_removes_the_file(session_file):
    desktop_link._save_session({"expires_at": 9e12, "user": {"user_id": 1}, "desktop_token": "t"})
    desktop_link._save_session(None)
    assert not session_file.exists()
