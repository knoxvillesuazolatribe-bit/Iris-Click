"""Wrong-try limits kept in pin_attempts, and the open sign-up limits."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.accounts import limits
from app.models.account_models import Device, DeviceAccount, PinAttempt, UserAccount
from app.models.user import User

T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)


def minutes(n):
    return T0 + timedelta(minutes=n)


def make(factory, users=1, devices=1):
    with factory() as db:
        people = [User(full_name=f"user{i}", role="assistive_user") for i in range(users)]
        computers = [Device(device_key_hash=f"{i:064d}") for i in range(devices)]
        db.add_all(people + computers)
        db.commit()
        return [p.user_id for p in people], [c.device_id for c in computers]


def wrong(db, times, device, user, start=0, step_s=10, **more):
    for i in range(times):
        limits.record_wrong_try(db, device_id=device, user_id=user, now=T0 + timedelta(seconds=start * 60 + i * step_s),
                                **more)


def test_a_fresh_account_has_five_tries(test_database):
    (u,), (d,) = make(test_database)
    with test_database() as db:
        state = limits.pin_state(db, device_id=d, user_id=u, now=T0)
        assert (state.status, state.tries_left, state.allowed) == ("ok", 5, True)


def test_tries_left_count_down(test_database):
    (u,), (d,) = make(test_database)
    with test_database() as db:
        for expected in (4, 3, 2, 1):
            wrong(db, 1, d, u, start=5 - expected)
            assert limits.pin_state(db, device_id=d, user_id=u, now=minutes(5)).tries_left == expected


def test_five_wrong_tries_mean_a_five_minute_wait(test_database):
    (u,), (d,) = make(test_database)
    with test_database() as db:
        wrong(db, 5, d, u)  # the fifth is at 00:40
        state = limits.pin_state(db, device_id=d, user_id=u, now=minutes(1))
        assert state.status == "wait" and not state.allowed
        assert 278 <= state.wait_seconds <= 282  # until 05:40 (5 min after the fifth try), seen at 01:00
        assert limits.pin_state(db, device_id=d, user_id=u, now=minutes(5)).status == "wait"
        after = limits.pin_state(db, device_id=d, user_id=u, now=minutes(6))
        assert (after.status, after.tries_left) == ("ok", 5)


def test_ten_wrong_tries_need_a_pin_reset_and_waiting_does_not_help(test_database):
    (u,), (d,) = make(test_database)
    with test_database() as db:
        wrong(db, 5, d, u)
        wrong(db, 4, d, u, start=10)
        assert limits.pin_state(db, device_id=d, user_id=u, now=minutes(12)).tries_left == 1
        wrong(db, 1, d, u, start=12)
        assert limits.pin_state(db, device_id=d, user_id=u, now=minutes(13)).status == "reset_needed"
        assert limits.pin_state(db, device_id=d, user_id=u, now=T0 + timedelta(days=30)).status == "reset_needed"


def test_a_lock_is_only_for_that_account_on_that_computer(test_database):
    (u1, u2), (d1, d2) = make(test_database, users=2, devices=2)
    with test_database() as db:
        wrong(db, 10, d1, u1)
        assert limits.pin_state(db, device_id=d1, user_id=u1, now=minutes(30)).status == "reset_needed"
        assert limits.pin_state(db, device_id=d2, user_id=u1, now=minutes(30)).status == "ok"  # their own PC still works
        assert limits.pin_state(db, device_id=d1, user_id=u2, now=minutes(30)).status == "ok"  # other people too


def test_a_correct_pin_clears_the_tries_on_that_computer_only(test_database):
    (u,), (d1, d2) = make(test_database, devices=2)
    with test_database() as db:
        wrong(db, 4, d1, u)
        wrong(db, 3, d2, u)
        limits.clear_wrong_tries(db, user_id=u, device_id=d1)
        assert limits.pin_state(db, device_id=d1, user_id=u, now=minutes(1)).tries_left == 5
        assert limits.pin_state(db, device_id=d2, user_id=u, now=minutes(1)).tries_left == 2


def test_admin_unlock_clears_every_computer_but_not_other_people(test_database):
    (u1, u2), (d1, d2) = make(test_database, users=2, devices=2)
    with test_database() as db:
        wrong(db, 10, d1, u1)
        wrong(db, 6, d2, u1)
        wrong(db, 2, d1, u2)
        limits.clear_wrong_tries(db, user_id=u1)
        assert limits.pin_state(db, device_id=d1, user_id=u1, now=minutes(2)).tries_left == 5
        assert limits.pin_state(db, device_id=d2, user_id=u1, now=minutes(2)).tries_left == 5
        assert limits.pin_state(db, device_id=d1, user_id=u2, now=minutes(2)).tries_left == 3


def test_twenty_wrong_tries_in_an_hour_across_computers_only_slow_things_down(test_database):
    (u,), devices = make(test_database, devices=6)
    with test_database() as db:
        for d in devices[:5]:
            wrong(db, 4, d, u)  # 20 tries, never 5 on one computer
        fresh = devices[5]
        state = limits.pin_state(db, device_id=fresh, user_id=u, now=minutes(10))
        assert state.status == "wait" and 0 < state.wait_seconds <= 3600
        later = limits.pin_state(db, device_id=fresh, user_id=u, now=minutes(61))
        assert (later.status, later.tries_left) == ("ok", 5)  # never a forced reset


def test_tries_with_unknown_usernames_count_against_the_computer(test_database):
    (u,), (d,) = make(test_database)
    with test_database() as db:
        wrong(db, 29, d, None)
        assert limits.pin_state(db, device_id=d, user_id=None, now=minutes(6)).status == "ok"
        wrong(db, 1, d, None, start=6)
        assert limits.pin_state(db, device_id=d, user_id=None, now=minutes(7)).status == "wait"
        assert limits.pin_state(db, device_id=d, user_id=u, now=minutes(7)).status == "wait"  # real accounts too
        assert limits.pin_state(db, device_id=d, user_id=None, now=minutes(70)).status == "ok"


def test_tries_count_against_the_visitors_address_without_storing_it(test_database):
    _, devices = make(test_database, devices=3)
    with test_database() as db:
        for d in devices:
            wrong(db, 20, d, None, address="203.0.113.7")
        assert limits.pin_state(db, device_id=None, user_id=None, address="203.0.113.7", now=minutes(5)).status == "wait"
        assert limits.pin_state(db, device_id=None, user_id=None, address="203.0.113.8", now=minutes(5)).status == "ok"
        stored = db.scalars(select(PinAttempt.address_hash)).all()
        assert all(len(value) == 64 and "203.0.113" not in value for value in stored)


def test_setup_code_tries_are_limited_per_computer_and_for_the_whole_site(test_database):
    _, devices = make(test_database, devices=8)
    with test_database() as db:
        first = devices[0]
        assert limits.setup_code_state(db, device_id=first, now=T0).tries_left == 5
        wrong(db, 4, first, None, kind="setup_code")
        assert limits.setup_code_state(db, device_id=first, now=minutes(1)).tries_left == 1
        wrong(db, 1, first, None, start=1, kind="setup_code")
        assert limits.setup_code_state(db, device_id=first, now=minutes(2)).status == "wait"
        assert limits.setup_code_state(db, device_id=devices[1], now=minutes(2)).status == "ok"
        assert limits.setup_code_state(db, device_id=first, now=minutes(17)).status == "ok"
        for d in devices[1:7]:
            wrong(db, 4, d, None, start=20, kind="setup_code")
        wrong(db, 1, devices[7], None, start=21, kind="setup_code")  # the 30th in the hour
        assert limits.setup_code_state(db, device_id=devices[7], now=minutes(22)).status == "wait"
        assert limits.setup_code_state(db, device_id=devices[7], now=minutes(90)).status == "ok"


def test_pin_tries_and_setup_code_tries_are_counted_apart(test_database):
    (u,), (d,) = make(test_database)
    with test_database() as db:
        wrong(db, 5, d, None, kind="setup_code")
        assert limits.pin_state(db, device_id=d, user_id=u, now=minutes(1)).tries_left == 5
        wrong(db, 5, d, u)
        assert limits.pin_state(db, device_id=d, user_id=u, now=minutes(2)).status == "wait"


def test_five_new_accounts_a_day_per_computer(test_database):
    people, (d1, d2) = make(test_database, users=7, devices=2)
    with test_database() as db:
        for i, user_id in enumerate(people[:5]):
            assert limits.signup_allowed(db, d1, now=minutes(i))
            db.add_all([UserAccount(user_id=user_id, username=f"user{i}", username_key=f"user{i}", created_at=minutes(i)),
                        DeviceAccount(device_id=d1, user_id=user_id, created_at=minutes(i))])
            db.commit()
        assert not limits.signup_allowed(db, d1, now=minutes(10))
        assert limits.signup_allowed(db, d2, now=minutes(10))
        assert limits.signup_allowed(db, d1, now=T0 + timedelta(days=1, minutes=10))
        # An older account that is only added to this computer today is not a new sign-up.
        db.add_all([UserAccount(user_id=people[5], username="old", username_key="old", created_at=T0 - timedelta(days=40)),
                    DeviceAccount(device_id=d2, user_id=people[5], created_at=minutes(1))])
        db.commit()
        assert limits.signup_allowed(db, d2, per_day=1, now=minutes(10))


def test_three_accounts_per_mobile_number(test_database):
    people, _ = make(test_database, users=4)
    with test_database() as db:
        for i, user_id in enumerate(people[:3]):
            assert limits.mobile_allowed(db, "+639178082488")
            db.add(UserAccount(user_id=user_id, username=f"m{i}xx", username_key=f"m{i}xx", mobile_number="+639178082488"))
            db.commit()
        assert not limits.mobile_allowed(db, "+639178082488")
        assert limits.mobile_allowed(db, "+639171234567")
