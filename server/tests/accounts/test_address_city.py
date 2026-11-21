"""The SOS location names the person's real city (Mandaue, Cebu City...), not always Lapu-Lapu."""

import pytest
from sqlalchemy import select

from app.models.user import User
from app.services import sos_service
from tests.accounts.test_my_address import api  # noqa: F401 - fixture


def test_a_mandaue_address_says_mandaue_city(api, test_database):  # noqa: F811
    saved = api.put("/api/accounts/me/address", json={
        "address": "12 Purok Mangga", "barangay": "Ibabo-Estancia", "city": "Mandaue City"})
    assert saved.status_code == 200
    assert saved.json() == {"location_text": "12 Purok Mangga, Barangay Ibabo-Estancia, Mandaue City"}
    with test_database() as db:
        assert db.scalars(select(User)).one().city == "Mandaue City"


def test_no_city_keeps_lapu_lapu_city(api, test_database):  # noqa: F811
    saved = api.put("/api/accounts/me/address", json={"address": "12 Purok Mangga", "barangay": "Pajo"})
    assert saved.json()["location_text"].endswith(", Lapu-Lapu City")
    with test_database() as db:
        assert db.scalars(select(User)).one().city is None


def test_a_typed_city_is_tidied(api):  # noqa: F811
    saved = api.put("/api/accounts/me/address", json={"address": "5 Rizal St.", "city": "  Talisay   City "})
    assert saved.json()["location_text"] == "5 Rizal St., Talisay City"


def test_a_city_that_is_too_long_is_refused(api):  # noqa: F811
    assert api.put("/api/accounts/me/address",
                   json={"address": "5 Rizal St.", "city": "X" * 61}).status_code == 422


@pytest.mark.parametrize(("city", "expected"), [
    (None, "Barangay Basak, Lapu-Lapu City"),
    ("", "Barangay Basak, Lapu-Lapu City"),
    ("   ", "Barangay Basak, Lapu-Lapu City"),
    ("Mandaue City", "Barangay Basak, Mandaue City"),
    ("Cordova", "Barangay Basak, Cordova"),
])
def test_basak_exists_in_two_cities_so_the_city_matters(city, expected):
    user = User(full_name="X", role="assistive_user", barangay="Basak", city=city)
    assert sos_service.location_text(user) == expected


def test_a_city_alone_is_not_a_location():
    user = User(full_name="X", role="assistive_user", city="Mandaue City")
    assert sos_service.location_text(user) is None
