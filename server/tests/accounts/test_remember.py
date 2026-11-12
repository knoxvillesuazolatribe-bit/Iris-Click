"""Remember me (build step 9): 30 days counted from the last use, renewed on every use."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.accounts import devices, service
from app.models.account_models import Device, DeviceAccount
from app.models.timestamps import as_utc, utc_now

PC = "R" * 43
PIN = "482913"


@pytest.fixture
def remembered(test_database):
    with test_database() as db:
        device = devices.remember_device(db, PC)
        made = service.sign_up(db, device, consent=True, username="mari_lapu", mobile_number="09178082488",
                               pin=PIN, pin_confirm=PIN, remember=True)
        return made.user.user_id


def test_each_use_renews_the_thirty_days(test_database, remembered):
    start = utc_now()
    with test_database() as db:
        device = db.scalars(select(Device)).one()
        for day in (20, 40, 60):  # never 30 days apart
            service.sign_in(db, device, user_id=remembered, now=start + timedelta(days=day))
        link = db.scalars(select(DeviceAccount)).one()
        assert as_utc(link.remembered_until) > start + timedelta(days=89)
        assert service.list_tiles(db, device, now=start + timedelta(days=89))[0].needs_pin is False


def test_thirty_days_without_use_asks_for_the_pin_and_the_pin_remembers_again(test_database, remembered):
    later = utc_now() + timedelta(days=31)
    with test_database() as db:
        device = db.scalars(select(Device)).one()
        with pytest.raises(service.AccountError) as refused:
            service.sign_in(db, device, user_id=remembered, now=later)
        assert refused.value.code == "pin_required"
        service.sign_in(db, device, user_id=remembered, pin=PIN, remember=True, now=later)
        assert service.list_tiles(db, device, now=later + timedelta(days=1))[0].needs_pin is False


def test_signing_in_with_a_pin_and_without_remember_me_turns_it_off(test_database, remembered):
    with test_database() as db:
        device = db.scalars(select(Device)).one()
        service.sign_in(db, device, user_id=remembered, pin=PIN, remember=False)
        assert service.list_tiles(db, device)[0].needs_pin is True


def test_sign_out_asks_for_the_pin_next_time(test_database, remembered):
    with test_database() as db:
        device = db.scalars(select(Device)).one()
        service.forget_remember_me(db, device, remembered)
        assert service.list_tiles(db, device)[0].needs_pin is True
        service.forget_remember_me(db, None, remembered)  # no computer ID: nothing to change, no error
