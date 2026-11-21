"""PDAO staff can set and change a person's city; the SOS location follows it."""

from sqlalchemy import select

from app.models.user import User


def test_admin_sets_the_city_on_the_profile(admin, make_user):
    ana = make_user("Ana Cruz")
    changed = admin.put(f"/api/admin/users/{ana}", json={
        "full_name": "Ana Cruz", "address": "12 Mabini St.", "barangay": "Basak", "city": "Mandaue City"}).json()
    assert changed["city"] == "Mandaue City"
    detail = admin.get(f"/api/admin/users/{ana}").json()
    assert detail["sos_location"] == "12 Mabini St., Barangay Basak, Mandaue City"
    assert detail["user"]["city"] == "Mandaue City"


def test_clearing_the_city_goes_back_to_lapu_lapu(admin, make_user):
    ana = make_user("Ana Cruz")
    admin.put(f"/api/admin/users/{ana}", json={
        "full_name": "Ana Cruz", "address": "12 Mabini St.", "city": "Cebu City"})
    admin.put(f"/api/admin/users/{ana}", json={"full_name": "Ana Cruz", "address": "12 Mabini St.", "city": ""})
    assert admin.get(f"/api/admin/users/{ana}").json()["sos_location"] == "12 Mabini St., Lapu-Lapu City"


def test_the_users_list_shows_the_city(admin, make_user, test_database):
    ana = make_user("Ana Cruz")
    with test_database() as db:
        db.get(User, ana).city = "Cordova"
        db.commit()
    rows = {u["full_name"]: u for u in admin.get("/api/admin/users").json()}
    assert rows["Ana Cruz"]["city"] == "Cordova"
    with test_database() as db:
        assert db.scalars(select(User).where(User.user_id == ana)).one().city == "Cordova"
