"""The calibration a new person does before their account exists (build step 8)."""

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.accounts import pending_calibration as pending
from app.api.routes import desktop_pending
from app.config import get_settings
from app.models.calibration_record import CalibrationRecord
from app.models.system_log import SystemLog
from app.models.timestamps import utc_now
from app.models.user import User
from app.services import active_user


@pytest.fixture(autouse=True)
def closed_window():
    pending.close_window()
    yield
    pending.close_window()


@pytest.fixture
def profiles(tmp_path):
    return tmp_path


def calibrate(factory, profiles, file_id, *, user_id=None, minutes_ago=1, status="Successful", on_disk=True):
    if on_disk:
        (profiles / f"{file_id}.json").write_text("{}", encoding="utf-8")
    with factory() as db:
        row = CalibrationRecord(user_id=user_id, profile_file_id=file_id, profile_name="New account",
                                accuracy_score=91.5, low_accuracy=False, status=status,
                                calibration_date=utc_now() - timedelta(minutes=minutes_ago))
        db.add(row)
        db.commit()
        return row.calibration_id


def person(factory, name="mari_lapu"):
    with factory() as db:
        user = User(full_name=name, role="assistive_user")
        db.add(user)
        db.commit()
        return user.user_id


def test_the_window_opens_for_fifteen_minutes_only():
    assert not pending.new_account_allowed(now=100.0)
    pending.allow_new_account(now=100.0)
    assert pending.new_account_allowed(now=100.0 + 14 * 60)
    assert not pending.new_account_allowed(now=100.0 + 15 * 60)
    pending.allow_new_account(now=0.0)
    pending.close_window()
    assert not pending.new_account_allowed(now=1.0)


def test_only_a_recent_successful_ownerless_calibration_on_disk_is_pending(test_database, profiles):
    calibrate(test_database, profiles, "old", minutes_ago=20)
    calibrate(test_database, profiles, "failed", status="Failed")
    calibrate(test_database, profiles, "owned", user_id=person(test_database))
    calibrate(test_database, profiles, "gone", on_disk=False)
    with test_database() as db:
        assert pending.find_pending(db, profiles) is None
    calibrate(test_database, profiles, "first", minutes_ago=5)
    calibrate(test_database, profiles, "newest", minutes_ago=2)
    with test_database() as db:
        found = pending.find_pending(db, profiles)
        assert (found.profile_file_id, found.accuracy_score, found.low_accuracy) == ("newest", 91.5, False)


def test_attach_gives_it_to_the_linked_person_and_uploads_it(test_database, profiles):
    calibrate(test_database, profiles, "newest")
    uid = person(test_database)
    active_user.set_user_id(uid)
    sent = []
    pending.allow_new_account()
    with test_database() as db:
        row, uploaded = pending.attach(db, profiles, "newest", upload=lambda r: sent.append(r.profile_file_id) or True)
        assert (row.user_id, uploaded, sent) == (uid, True, ["newest"])
        assert not pending.new_account_allowed()
        assert pending.find_pending(db, profiles) is None
        assert db.scalars(select(SystemLog.activity_type)).all() == ["calibration_attached"]


def test_attach_needs_someone_linked_and_something_pending(test_database, profiles):
    active_user.set_user_id(None)
    with test_database() as db:
        with pytest.raises(pending.PendingError) as refused:
            pending.attach(db, profiles)
        assert refused.value.status_code == 409
    active_user.set_user_id(person(test_database))
    with test_database() as db:
        with pytest.raises(pending.PendingError) as refused:
            pending.attach(db, profiles)
        assert refused.value.status_code == 404
    calibrate(test_database, profiles, "newest")
    with test_database() as db:
        with pytest.raises(pending.PendingError):
            pending.attach(db, profiles, "some-other-id")


def test_a_failed_upload_still_attaches(test_database, profiles):
    calibrate(test_database, profiles, "newest")
    uid = person(test_database)
    active_user.set_user_id(uid)

    def broken(_row):
        raise OSError("no network")

    with test_database() as db:
        row, uploaded = pending.attach(db, profiles, upload=broken)
        assert (row.user_id, uploaded) == (uid, False)


def test_discard_deletes_the_file_and_the_row(test_database, profiles):
    calibrate(test_database, profiles, "newest")
    owned = calibrate(test_database, profiles, "owned", user_id=person(test_database))
    pending.allow_new_account()
    with test_database() as db:
        assert pending.discard(db, profiles, "newest") is True
        assert not (profiles / "newest.json").exists() and not pending.new_account_allowed()
        assert pending.discard(db, profiles) is False  # nothing left to discard
        assert db.get(CalibrationRecord, owned) is not None and (profiles / "owned.json").exists()


def test_the_routes(test_database, profiles, monkeypatch):
    settings = get_settings().model_copy(update={"profiles_dir": profiles})
    monkeypatch.setattr(desktop_pending, "get_settings", lambda: settings)
    monkeypatch.setattr(pending, "upload_to_hosted", lambda _row: False)
    app = FastAPI()
    app.include_router(desktop_pending.router, prefix="/api")
    client = TestClient(app)
    assert client.get("/api/desktop/pending-calibration").json() == {
        "pending": False, "profile_file_id": None, "accuracy_score": None, "low_accuracy": False}
    assert client.post("/api/desktop/pending-calibration/allow").json() == {"allowed": True}
    assert pending.new_account_allowed()
    calibrate(test_database, profiles, "newest")
    assert client.get("/api/desktop/pending-calibration").json()["profile_file_id"] == "newest"
    active_user.set_user_id(None)
    assert client.post("/api/desktop/pending-calibration/attach", json={}).status_code == 409
    active_user.set_user_id(person(test_database))
    assert client.post("/api/desktop/pending-calibration/attach", json={"profile_file_id": "newest"}).json() == {
        "attached": True, "uploaded": False}
    assert client.post("/api/desktop/pending-calibration/discard", json={}).json() == {"discarded": False}
