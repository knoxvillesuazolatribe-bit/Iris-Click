"""The new account reaches IrisClick Desktop by sync a few seconds after sign-up (found in a live test).

Attaching the new-account calibration before that used to fail with a database error, leaving the
calibration ownerless. Now attach syncs once, and if the account is still not here it says "not ready"
(409) so the website tries again.
"""

from datetime import timedelta

import pytest

from app.accounts import pending_calibration as pending
from app.models.calibration_record import CalibrationRecord
from app.models.timestamps import utc_now
from app.models.user import User
from app.services import active_user


@pytest.fixture(autouse=True)
def closed_window():
    pending.close_window()
    yield
    pending.close_window()


def calibrate(factory, profiles, file_id="newest"):
    (profiles / f"{file_id}.json").write_text("{}", encoding="utf-8")
    with factory() as db:
        db.add(CalibrationRecord(user_id=None, profile_file_id=file_id, profile_name="New account",
                                 accuracy_score=91.5, low_accuracy=False, status="Successful",
                                 calibration_date=utc_now() - timedelta(minutes=1)))
        db.commit()


def test_the_account_arrives_by_sync_then_the_calibration_is_attached(test_database, tmp_path):
    calibrate(test_database, tmp_path)
    active_user.set_user_id(42)  # linked on the website, not yet copied to this computer
    synced = []

    def sync_now():  # what the desktop sync does: copy the account down
        synced.append(1)
        with test_database() as db:
            db.add(User(user_id=42, full_name="knox", role="assistive_user"))
            db.commit()

    with test_database() as db:
        row, uploaded = pending.attach(db, tmp_path, "newest", upload=lambda r: True, sync_now=sync_now)
    assert synced == [1] and row.user_id == 42 and uploaded is True


def test_still_not_here_says_not_ready_and_keeps_the_calibration(test_database, tmp_path):
    calibrate(test_database, tmp_path)
    active_user.set_user_id(42)
    with test_database() as db:
        with pytest.raises(pending.PendingError) as refused:
            pending.attach(db, tmp_path, "newest", upload=lambda r: True, sync_now=lambda: None)
        assert refused.value.status_code == 409 and refused.value.message == pending.NOT_READY
        assert pending.find_pending(db, tmp_path) is not None  # still there for the next try


def test_an_offline_sync_is_also_just_not_ready(test_database, tmp_path):
    calibrate(test_database, tmp_path)
    active_user.set_user_id(42)

    def offline():
        raise OSError("no network")

    with test_database() as db:
        with pytest.raises(pending.PendingError) as refused:
            pending.attach(db, tmp_path, "newest", upload=lambda r: True, sync_now=offline)
    assert refused.value.status_code == 409
