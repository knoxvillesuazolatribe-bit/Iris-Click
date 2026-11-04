import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.calibration_record import CalibrationRecord
from app.services import active_user, assistive_service
from app.services.background_db import writer
from app.services.session_service import COOKIE_NAME

from tests.auth.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, add_calibration, logs
# The calibration WebSocket fixture and helpers (fake camera, temp profile dir).
from tests.api.test_calibration_ws import FakeTracker, _receive, _start, client  # noqa: F401


def _tiles(api):
    response = api.get("/api/assistive/users")
    assert response.status_code == 200
    return {tile["full_name"]: tile for tile in response.json()}


def _profile_file(profiles_dir, file_id):
    (profiles_dir / f"{file_id}.json").write_text("{}", encoding="utf-8")


def test_tiles_list_only_active_assistive_users_alphabetically(api, make_user, admin_id):
    make_user("Carla Diaz")
    make_user("Ana Cruz")
    make_user("Hidden Person", status="inactive")
    names = [tile["full_name"] for tile in api.get("/api/assistive/users").json()]
    assert names == ["Ana Cruz", "Carla Diaz"]


def test_no_users_gives_an_empty_list(api):
    assert api.get("/api/assistive/users").json() == []


def test_continue_needs_a_saved_calibration(api, make_user):
    make_user("Ana Cruz")
    tile = _tiles(api)["Ana Cruz"]
    assert tile["continue_profile_id"] is None
    assert tile["continue_unavailable_reason"] == assistive_service.NO_CALIBRATION
    assert tile["last_calibrated_at"] is None and tile["accuracy_score"] is None


def test_continue_uses_the_latest_profile_on_this_computer(api, make_user, test_database,
                                                           profiles_dir):
    user_id = make_user("Ana Cruz")
    add_calibration(test_database, user_id, file_id="old",
                    when=datetime(2026, 11, 1, tzinfo=UTC), accuracy="91.00")
    add_calibration(test_database, user_id, file_id="new",
                    when=datetime(2026, 11, 3, tzinfo=UTC), accuracy="95.50")
    add_calibration(test_database, user_id, status="Failed",
                    when=datetime(2026, 11, 4, tzinfo=UTC), accuracy=None)
    _profile_file(profiles_dir, "old")
    _profile_file(profiles_dir, "new")

    tile = _tiles(api)["Ana Cruz"]
    assert tile["continue_profile_id"] == "new"
    assert tile["continue_unavailable_reason"] is None
    assert tile["accuracy_score"] == "95.50"
    assert tile["last_calibrated_at"].startswith("2026-11-03")


def test_profile_missing_from_this_computer_is_explained(api, make_user, test_database,
                                                         profiles_dir):
    user_id = make_user("Ana Cruz")
    add_calibration(test_database, user_id, file_id="made-elsewhere")
    tile = _tiles(api)["Ana Cruz"]
    assert tile["continue_profile_id"] is None
    assert tile["continue_unavailable_reason"] == assistive_service.NOT_ON_THIS_COMPUTER


def test_selecting_a_tile_signs_in_and_sets_the_active_user(api, make_user, test_database):
    user_id = make_user("Ana Cruz")
    response = api.post("/api/assistive/select", json={"user_id": user_id})

    assert response.status_code == 200
    assert response.json() == {"user_id": user_id, "full_name": "Ana Cruz",
                               "role": "assistive_user"}
    assert api.get("/api/auth/me").json()["role"] == "assistive_user"
    assert active_user.get_user_id() == user_id
    [log] = logs(test_database, "user_selected")
    assert log.user_id == user_id


def test_active_user_survives_a_restart(tmp_path):
    path = tmp_path / "active_user.json"
    active_user.use_path(path)
    active_user.set_user_id(7)
    assert json.loads(path.read_text("utf-8")) == {"user_id": 7}
    active_user.use_path(path)  # as a fresh process would
    assert active_user.get_user_id() == 7
    active_user.set_user_id(None)
    assert not path.exists()


def test_unreadable_active_user_file_is_ignored(tmp_path):
    path = tmp_path / "active_user.json"
    path.write_text("not json", encoding="utf-8")
    active_user.use_path(path)
    assert active_user.get_user_id() is None


def test_inactive_or_unknown_users_cannot_be_selected(api, make_user, admin_id):
    inactive = make_user("Old User", status="inactive")
    assert api.post("/api/assistive/select", json={"user_id": inactive}).status_code == 403
    assert api.post("/api/assistive/select", json={"user_id": 9999}).status_code == 404
    assert api.post("/api/assistive/select", json={"user_id": admin_id}).status_code == 404
    assert active_user.get_user_id() is None


def test_assistive_logout_clears_the_active_user(api, make_user, test_database):
    user_id = make_user("Ana Cruz")
    api.post("/api/assistive/select", json={"user_id": user_id})
    assert api.post("/api/auth/logout").status_code == 204
    assert active_user.get_user_id() is None
    assert api.get("/api/auth/me").status_code == 401


def test_admin_sign_in_keeps_the_assistive_user_tracking(api, make_user, admin_id):
    user_id = make_user("Ana Cruz")
    api.post("/api/assistive/select", json={"user_id": user_id})
    old_token = api.cookies.get(COOKIE_NAME)
    api.post("/api/auth/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})

    assert api.get("/api/auth/me").json()["role"] == "admin"
    assert active_user.get_user_id() == user_id  # calibrations still credited to Ana
    api.cookies.set(COOKIE_NAME, old_token, path="/api")
    assert api.get("/api/auth/me").status_code == 401  # the replaced session is revoked


def test_calibration_after_selection_is_saved_under_that_user(client, make_user,  # noqa: F811
                                                              test_database):
    user_id = make_user("Ana Cruz")
    assert client.post("/api/assistive/select", json={"user_id": user_id}).status_code == 200

    with client.websocket_connect("/api/ws/calibration") as ws:
        ready = _start(ws)
        tracker = FakeTracker.instances[-1]
        for index, point in enumerate(ready["points"]):
            tracker.target = (point["x"], point["y"])
            ws.send_json({"type": "collect", "index": index})
            _receive(ws, "point_result")
        assert _receive(ws, "result")["status"] == "success"

    writer.wait_idle(5)
    with test_database() as session:
        record = session.scalars(select(CalibrationRecord)).one()
    assert record.user_id == user_id
