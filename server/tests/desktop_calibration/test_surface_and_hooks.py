import json

import pytest

from app import launcher
from app.desktop_calibration import hooks, surface
from app.desktop_calibration.window import dot_position, profile_name
from app.core.calibration.collector import CALIBRATION_POINTS


@pytest.fixture(autouse=True)
def no_env(monkeypatch):
    monkeypatch.delenv(surface.ENV_NAME, raising=False)


def test_default_is_web(tmp_path):
    assert surface.surface(tmp_path / "missing.env") == "web"


@pytest.mark.parametrize("text, expected", [
    ("IRISCLICK_CALIBRATION_SURFACE=desktop\n", "desktop"),
    ("IRISCLICK_CALIBRATION_SURFACE=Desktop\n", "desktop"),
    ("IRISCLICK_CALIBRATION_SURFACE=web\n", "web"),
    ("IRISCLICK_CALIBRATION_SURFACE=sideways\n", "web"),
    ("OTHER=1\n", "web"),
])
def test_value_from_env_file(tmp_path, text, expected):
    env = tmp_path / ".env"
    env.write_text(text, encoding="utf-8")
    assert surface.surface(env) == expected


def test_switching_back_is_instant(tmp_path):
    env = tmp_path / ".env"
    env.write_text("IRISCLICK_CALIBRATION_SURFACE=desktop\n", encoding="utf-8")
    assert surface.surface(env) == "desktop"
    env.write_text("IRISCLICK_CALIBRATION_SURFACE=web\n", encoding="utf-8")
    assert surface.surface(env) == "web"


def test_process_environment_wins(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("IRISCLICK_CALIBRATION_SURFACE=web\n", encoding="utf-8")
    monkeypatch.setenv(surface.ENV_NAME, "desktop")
    assert surface.surface(env) == "desktop"


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return json.dumps(self.body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_open_window_posts_to_the_local_server():
    seen = []

    def opener(request, timeout):
        seen.append((request.full_url, json.loads(request.data), request.get_method()))
        return FakeResponse({"opened": True})

    assert hooks.open_window("recalibrate", port=8123, opener=opener) is True
    assert seen == [("http://127.0.0.1:8123/api/desktop/calibration/open",
                     {"reason": "recalibrate", "first_run": False}, "POST")]


def test_open_window_never_raises():
    def opener(request, timeout):
        raise OSError("refused")

    assert hooks.open_window(port=8123, opener=opener) is False


def test_first_run_does_nothing_in_web_mode(monkeypatch):
    monkeypatch.setattr(hooks, "open_window", lambda *a, **k: pytest.fail("must not open"))
    monkeypatch.setattr(hooks, "surface", lambda: "web")
    assert hooks.first_run_calibration(8000) is False


def test_first_run_asks_the_server_in_desktop_mode(monkeypatch):
    calls = []
    monkeypatch.setattr(hooks, "surface", lambda: "desktop")
    monkeypatch.setattr(hooks, "open_window", lambda *a, **k: calls.append((a, k)) or True)
    assert hooks.first_run_calibration(8000) is True
    assert calls == [(("first_run",), {"first_run": True, "port": 8000})]


def test_launcher_hook_is_silent_on_any_failure(monkeypatch):
    def broken(port):
        raise RuntimeError("boom")

    monkeypatch.setattr(hooks, "first_run_calibration", broken)
    assert launcher.first_run_calibration(8000) is False


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5])
def test_dot_positions_in_physical_pixels(scale):
    # Windows reports the physical size to a DPI-aware process (display.enable_dpi_awareness).
    screen = (round(1536 * scale), round(864 * scale))
    for x, y in CALIBRATION_POINTS:
        px, py = dot_position((x, y), screen)
        assert px == round(x * screen[0]) and py == round(y * screen[1])
        assert 0 < px < screen[0] and 0 < py < screen[1]
    # The 4% edge stays on screen at every scale.
    assert dot_position((0.04, 0.96), screen) == (round(0.04 * screen[0]), round(0.96 * screen[1]))


def test_profile_name_fits_the_engine_limit():
    assert 0 < len(profile_name()) <= 60
