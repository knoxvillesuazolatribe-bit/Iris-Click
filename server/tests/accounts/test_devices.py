import hashlib

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.accounts import device_id, devices
from app.api.routes import desktop_device
from app.models.account_models import Device


def test_the_computer_id_is_made_once_and_kept(tmp_path):
    path = tmp_path / "storage" / "device_id.txt"
    first = device_id.this_computer_id(path)
    assert device_id.is_device_id(first) and path.read_text(encoding="ascii") == first
    assert device_id.this_computer_id(path) == first
    assert not path.with_suffix(".tmp").exists()


def test_two_computers_get_different_ids(tmp_path):
    assert device_id.this_computer_id(tmp_path / "a.txt") != device_id.this_computer_id(tmp_path / "b.txt")


def test_a_damaged_or_empty_file_is_replaced(tmp_path):
    path = tmp_path / "device_id.txt"
    for damaged in (b"", b"short", b"has spaces and !!! in it, long enough though", b"\xff\xfe\x00"):
        path.write_bytes(damaged)
        fresh = device_id.this_computer_id(path)
        assert device_id.is_device_id(fresh) and device_id.this_computer_id(path) == fresh


def test_what_counts_as_a_computer_id():
    assert device_id.is_device_id("a" * 32) and device_id.is_device_id("A-b_9" * 8)
    for bad in (None, 123, "", "a" * 31, "a" * 65, "a" * 31 + "/", "a" * 31 + " ", "a" * 32 + "\n"):
        assert not device_id.is_device_id(bad)


def test_only_the_hash_of_the_id_is_stored(test_database):
    key = "k" * 43
    with test_database() as db:
        device = devices.remember_device(db, key)
        assert device.device_key_hash == hashlib.sha256(key.encode()).hexdigest() != key
        assert device.is_shared is False and device.last_seen_at is not None
    with test_database() as db:
        assert key not in [str(v) for row in db.execute(select(Device.__table__)).all() for v in row]


def test_the_same_computer_is_stored_once(test_database):
    with test_database() as db:
        first = devices.remember_device(db, "k" * 43).device_id
        assert devices.remember_device(db, "k" * 43).device_id == first
        assert devices.remember_device(db, "m" * 43).device_id != first
        assert len(db.scalars(select(Device)).all()) == 2
        assert devices.find_device(db, "k" * 43).device_id == first


def test_an_unknown_or_bad_id_finds_nothing_and_adds_nothing(test_database):
    with test_database() as db:
        assert devices.find_device(db, "z" * 43) is None
        for bad in (None, "", "short", "x" * 200, "a" * 31 + "'"):
            assert devices.find_device(db, bad) is None and devices.remember_device(db, bad) is None
        assert db.scalars(select(Device)).all() == []


def test_desktop_gives_the_website_this_computers_id(tmp_path, monkeypatch):
    monkeypatch.setattr(device_id, "DEVICE_ID_PATH", tmp_path / "device_id.txt")
    app = FastAPI()
    app.include_router(desktop_device.router, prefix="/api")
    client = TestClient(app)
    response = client.get("/api/desktop/device")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    value = response.json()["device_id"]
    assert device_id.is_device_id(value) and client.get("/api/desktop/device").json() == {"device_id": value}
    assert (tmp_path / "device_id.txt").read_text(encoding="ascii") == value


def test_the_pc_server_answers_the_computer_id_check(tmp_path, monkeypatch):
    monkeypatch.setattr(device_id, "DEVICE_ID_PATH", tmp_path / "device_id.txt")
    from app.api import main
    client = TestClient(main.create_app())
    response = client.get("/api/desktop/device")
    assert response.status_code == 200 and device_id.is_device_id(response.json()["device_id"])
    blocked = client.get("/api/desktop/device", headers={"Origin": "https://not-irisclick.example"})
    assert blocked.status_code == 403 and "device_id" not in blocked.text
