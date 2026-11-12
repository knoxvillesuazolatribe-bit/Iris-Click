"""After a new person calibrates, eye tracking stays off until their account exists."""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.accounts import pending_calibration as pending
from app.api.routes import desktop_pending
from app.services import active_user


@pytest.fixture(autouse=True)
def own_file(tmp_path):
    active_user.use_path(tmp_path / "active_user.json")
    yield
    active_user.set_user_id(None)


def test_nobody_linked_stops_tracking_now_and_again_a_moment_later():
    stops, waits = [], []
    assert pending.hold_tracking(stop=lambda: stops.append(1), delays_s=(1.0, 2.0), wait=waits.append) is True
    for _ in range(50):  # the re-checks run on a short-lived thread
        if len(stops) == 3:
            break
        time.sleep(0.01)
    assert stops == [1, 1, 1] and waits == [1.0, 2.0]


def test_tracking_for_a_linked_person_is_never_touched():
    active_user.set_user_id(7)
    stops = []
    assert pending.hold_tracking(stop=lambda: stops.append(1), delays_s=()) is False
    assert stops == []


def test_a_person_linked_meanwhile_keeps_their_tracking():
    stops = []

    def link_then_wait(_delay):
        active_user.set_user_id(7)  # the account was created and linked before the re-check

    pending.hold_tracking(stop=lambda: stops.append(1), delays_s=(1.0,), wait=link_then_wait)
    time.sleep(0.1)
    assert stops == [1]


def test_the_route_answers_held(monkeypatch):
    calls = []
    monkeypatch.setattr(pending, "hold_tracking", lambda: calls.append(1) or True)
    app = FastAPI()
    app.include_router(desktop_pending.router, prefix="/api")
    assert TestClient(app).post("/api/desktop/pending-calibration/hold-tracking").json() == {"held": True}
    assert calls == [1]
