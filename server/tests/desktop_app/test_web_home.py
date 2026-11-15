"""One home, on the web: the control bar's Home goes to the website's Home in the IrisClick window."""

import asyncio

from fastapi.testclient import TestClient

from app.desktop_calibration.relay import Relay
from app.workers import web_home


class FakeSite:
    def __init__(self):
        self.sent = []

    async def send_json(self, message):
        self.sent.append(message)


def test_relay_asks_every_open_page_to_go_home():
    relay = Relay(spawn=lambda port, reason: 1)
    pages = [FakeSite(), FakeSite()]
    for page in pages:
        relay.add_site(page)
    assert asyncio.run(relay.go_home()) == 2
    assert all(page.sent[-1]["type"] == "app.go_home" for page in pages)


def test_no_open_page_reports_zero():
    assert asyncio.run(Relay(spawn=lambda port, reason: 1).go_home()) == 0


def test_open_pages_are_asked_and_no_window_opens():
    opened = []
    result = web_home.go_home(8000, post=lambda url: {"pages": 1}, open_window=lambda: opened.append(1))
    assert result == "pages" and opened == []


def test_without_an_open_page_the_irisclick_window_opens_at_home():
    opened = []
    assert web_home.go_home(8000, post=lambda url: {"pages": 0},
                            open_window=lambda: opened.append(1)) == "window"
    assert opened == [1]


def test_a_silent_server_still_opens_home():
    def down(url):
        raise OSError("refused")
    opened = []
    assert web_home.go_home(8000, post=down, open_window=lambda: opened.append(1)) == "window"
    assert opened == [1]


def test_home_window_uses_the_hosted_website_never_a_developer_address(monkeypatch):
    from app import launcher
    calls = []
    monkeypatch.setattr(launcher, "website_url", lambda: "https://iris-click.vercel.app/")
    monkeypatch.setattr(launcher, "find_edge", lambda: None)
    monkeypatch.setattr(launcher, "open_window", lambda url, edge: calls.append(url))
    web_home._open_home_window()
    assert calls == ["https://iris-click.vercel.app/home"]


def test_web_pages_cannot_call_the_route():
    from app.api.main import create_app
    client = TestClient(create_app())
    refused = client.post("/api/desktop/go-home", headers={"Origin": "https://evil.example"})
    assert refused.status_code == 403
    allowed = client.post("/api/desktop/go-home")
    assert allowed.status_code == 200 and allowed.json() == {"pages": 0}
