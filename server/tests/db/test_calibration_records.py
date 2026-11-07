import threading
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import database
from app.models.calibration_record import CalibrationRecord
from app.models.system_log import SystemLog
from app.models.user import User
from app.schemas.calibration import CalibrationProfileFile
from app.services import active_user, calibration_records, calibration_service
from app.services.background_db import writer
# The calibration WebSocket fixture and helpers (fake camera, temp profile dir).
from tests.api.test_calibration_ws import FakeTracker, _receive, _start, client  # noqa: F401


def _profile(**overrides) -> CalibrationProfileFile:
    values = dict(
        id="20261104T120000-abcd1234", profile_name="Desk",
        created_at=datetime(2026, 11, 4, 12, 0, tzinfo=UTC), feature_source="nose_eye",
        accuracy_fraction=0.0423, low_accuracy=False, sample_count=410,
        camera_index=1, deep_gaze_available=True,
        candidates=[{"feature_source": "nose_eye", "error_fraction": 0.0423}],
        model={"kind": "test"},
    )
    values.update(overrides)
    return CalibrationProfileFile.model_validate(values)


def _rows(factory, model):
    writer.wait_idle(5)
    with factory() as session:
        return session.scalars(select(model)).all()


def _add_user(factory) -> int:
    with factory() as session:
        user = User(full_name="Ana Cruz", role="assistive_user")
        session.add(user)
        session.commit()
        return user.user_id


@pytest.mark.parametrize("error, expected", [
    (0.0423, Decimal("95.77")), (0.05, Decimal("95.00")), (0.0, Decimal("100.00")),
    (1.4, Decimal("0.00")), (-0.2, Decimal("100.00")), (None, None),
])
def test_accuracy_percent(error, expected):
    assert calibration_records.accuracy_percent(error) == expected


def test_record_success_copies_the_profile_and_logs_it(test_database):
    user_id = _add_user(test_database)
    active_user.set_user_id(user_id)
    calibration_records.record_success(_profile())

    [row] = _rows(test_database, CalibrationRecord)
    assert row.status == "Successful"
    assert row.user_id == user_id
    assert row.profile_file_id == "20261104T120000-abcd1234"
    assert row.accuracy_score == Decimal("95.77")
    assert row.error_fraction == pytest.approx(0.0423)
    assert row.calibration_data["model"] == {"kind": "test"}
    assert row.camera_index == 1 and row.sample_count == 410
    [log] = _rows(test_database, SystemLog)
    assert log.activity_type == "calibration" and log.user_id == user_id
    assert "95.77%" in log.activity_description


def test_record_failure_without_a_signed_in_user(test_database):
    calibration_records.record_failure("Desk", "not_accurate_enough", 0, 0.14, "iris_ring")

    [row] = _rows(test_database, CalibrationRecord)
    assert (row.status, row.user_id, row.profile_file_id) == ("Failed", None, None)
    assert row.accuracy_score == Decimal("86.00")
    assert row.failure_reason == calibration_records.FAILURE_REASONS["not_accurate_enough"]
    [log] = _rows(test_database, SystemLog)
    assert log.activity_type == "calibration_failed"


def test_a_database_error_is_logged_not_raised(monkeypatch, caplog):
    def broken():
        raise RuntimeError("database down")

    monkeypatch.setattr(database, "get_session_factory", broken)
    calibration_records.record_failure("Desk", "fit_failed", 0)
    assert writer.wait_idle(5)
    assert "database down" in caplog.text


def _calibrate(client):
    with client.websocket_connect("/api/ws/calibration") as ws:
        ready = _start(ws)
        tracker = FakeTracker.instances[-1]
        for index, point in enumerate(ready["points"]):
            tracker.target = (point["x"], point["y"])
            ws.send_json({"type": "collect", "index": index})
            _receive(ws, "point_result")
        return _receive(ws, "result")


def test_successful_calibration_is_also_saved_to_the_database(client, test_database, tmp_path):
    result = _calibrate(client)

    assert result["status"] == "success"
    assert len(list(tmp_path.glob("*.json"))) == 1  # the JSON file is still written
    [row] = _rows(test_database, CalibrationRecord)
    assert row.status == "Successful"
    assert row.profile_file_id == result["profile"]["id"]
    assert row.accuracy_score == calibration_records.accuracy_percent(
        result["profile"]["accuracy_fraction"])


def test_failed_dot_is_saved_as_failed(client, test_database):
    with client.websocket_connect("/api/ws/calibration") as ws:
        _start(ws)
        FakeTracker.instances[-1].closed_eyes = True
        for _ in range(2):
            ws.send_json({"type": "collect", "index": 0})
            _receive(ws, "point_result")
        assert _receive(ws, "result")["status"] == "failed"

    [row] = _rows(test_database, CalibrationRecord)
    assert row.status == "Failed"
    assert row.failure_reason == calibration_records.FAILURE_REASONS["dot_not_clear"]


def test_rejected_fit_is_saved_with_its_accuracy(client, test_database, monkeypatch):
    rejected = SimpleNamespace(accepted=False, accuracy=0.14,
                               model=SimpleNamespace(feature_source="iris_ring"))
    monkeypatch.setattr(calibration_service, "fit_hybrid", lambda *args: rejected)
    assert _calibrate(client)["status"] == "failed"

    [row] = _rows(test_database, CalibrationRecord)
    assert (row.status, row.feature_source, row.accuracy_score) == (
        "Failed", "iris_ring", Decimal("86.00"))


def test_fit_error_is_saved_as_failed(client, test_database, monkeypatch):
    def no_fit(*args):
        raise ValueError("singular matrix")

    monkeypatch.setattr(calibration_service, "fit_hybrid", no_fit)
    assert _calibrate(client)["status"] == "failed"

    [row] = _rows(test_database, CalibrationRecord)
    assert row.failure_reason == calibration_records.FAILURE_REASONS["fit_failed"]


def test_calibration_still_succeeds_when_the_database_is_down(client, tmp_path, monkeypatch):
    def broken():
        raise RuntimeError("database down")

    monkeypatch.setattr(database, "get_session_factory", broken)
    result = _calibrate(client)

    assert result["status"] == "success" and result["worker_started"] is True
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_a_slow_database_does_not_delay_the_result(client, test_database, monkeypatch):
    release = threading.Event()

    def slow_factory():
        release.wait(10)
        return test_database

    monkeypatch.setattr(database, "get_session_factory", slow_factory)
    try:
        result = _calibrate(client)  # returns while the database write is still blocked
        assert result["status"] == "success"
        assert not release.is_set()
    finally:
        release.set()
    assert len(_rows(test_database, CalibrationRecord)) == 1
