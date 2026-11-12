"""Username, mobile number and PIN rules (pure logic) for accounts on this computer."""

import pytest

from app.accounts import mobiles, pins, usernames
from app.models.account_models import UserAccount
from app.models.user import User
from app.services import word_filter_service


def add_account(factory, username, mobile=None):
    with factory() as db:
        user = User(full_name=username, role="assistive_user")
        db.add(user)
        db.flush()
        db.add(UserAccount(user_id=user.user_id, username=username, username_key=usernames.username_key(username),
                           mobile_number=mobile))
        db.commit()
        return user.user_id


# ---------- usernames ----------

@pytest.mark.parametrize("name", ["mari", "Mari_Lapu", "mia.2", "j0n", "a" * 20, "abc", "x_y.z9"])
def test_good_usernames(name):
    assert usernames.username_problem(name) is None


@pytest.mark.parametrize("name, problem", [
    ("", "too_short"), ("ab", "too_short"), (None, "too_short"), (123, "too_short"),
    ("a" * 21, "too_long"),
    ("mari lapu", "bad_characters"), ("mari-lapu", "bad_characters"), ("mari@pdao", "bad_characters"),
    ("mañana", "bad_characters"), ("mari\n", "bad_characters"), ("<b>mari", "bad_characters"),
    ("123", "needs_letter"), ("1_2.3", "needs_letter"),
    ("_mari", "bad_edges"), ("mari.", "bad_edges"), (".mari_", "bad_edges"),
    ("admin", "reserved"), ("ADMIN", "reserved"), ("Admin1", "reserved"), ("pdao", "reserved"),
    ("IrisClick", "reserved"), ("support", "reserved"),
])
def test_usernames_that_are_refused(name, problem):
    assert usernames.username_problem(name) == problem


def test_a_name_that_only_contains_a_reserved_word_is_fine():
    assert usernames.username_problem("administer") is None and usernames.username_problem("rootbeer") is None


def test_usernames_are_taken_without_regard_to_case(test_database):
    add_account(test_database, "Mari_Lapu")
    with test_database() as db:
        assert usernames.is_taken(db, "mari_lapu") and usernames.is_taken(db, "MARI_LAPU")
        assert not usernames.is_taken(db, "mari_lapu2")
        assert usernames.check_username(db, "MARI_lapu") == "taken"
        assert usernames.check_username(db, "mia") is None
        assert usernames.check_username(db, "ab") == "too_short"


def test_suggestions_are_free_valid_and_different(test_database):
    add_account(test_database, "mari_lapu")
    add_account(test_database, "mari_lapu2")
    with test_database() as db:
        found = usernames.suggestions(db, "mari_lapu")
        assert len(found) == 3 == len(set(found)) and "mari_lapu2" not in found
        assert all(usernames.check_username(db, name) is None for name in found)
        long_name = "a" * 20
        assert all(len(name) <= 20 for name in usernames.suggestions(db, long_name))


def test_filtered_words_cannot_be_usernames(test_database):
    with test_database() as db:
        admin = User(full_name="PDAO Admin", role="admin", email="admin@pdao.ph", password_hash="$argon2id$fake")
        db.add(admin)
        db.commit()
        word_filter_service.add_word(db, admin, "zorblat", "other", "blocked")  # an invented word
        assert usernames.check_username(db, "zorblat") == "not_allowed"
        assert usernames.check_username(db, "Zorblat") == "not_allowed"
        assert usernames.check_username(db, "z_o_r_b_l_a_t") == "not_allowed"
        assert usernames.check_username(db, "mari.zorblat") == "not_allowed"
        assert usernames.check_username(db, "zorro") is None


# ---------- mobile numbers ----------

@pytest.mark.parametrize("text", ["09178082488", "0917 808 2488", "0917-808-2488", "+639178082488",
                                  "639178082488", "+63 917 808 2488", "9178082488", " 09178082488 "])
def test_mobile_numbers_are_stored_one_way(text):
    assert mobiles.normalize_mobile(text) == "+639178082488"


@pytest.mark.parametrize("text", ["", None, 9178082488, "0917808248", "091780824888", "08178082488",
                                  "+15551234567", "0917808248a", "++639178082488", "032 255 1234", "0917 808 2488 x"])
def test_what_is_not_a_mobile_number(text):
    assert mobiles.normalize_mobile(text) is None


def test_mobile_numbers_are_shown_masked():
    assert mobiles.mask_mobile("+639178082488") == "09** *** 2488"
    assert "9178" not in mobiles.mask_mobile("+639178082488")
    assert mobiles.mask_mobile(None) == "" and mobiles.mask_mobile("09178082488") == ""


# ---------- PINs ----------

@pytest.mark.parametrize("pin", ["482913", "907351", "135790", "246813", "100200", "864209"])
def test_good_pins(pin):
    assert pins.pin_problem(pin) is None


@pytest.mark.parametrize("pin", ["", "12345", "1234567", "12345a", "12 345", " 123456", None, 482913,
                                 "١٢٣٤٥٦", "48291\n"])
def test_a_pin_is_exactly_six_digits(pin):
    assert pins.pin_problem(pin) == "not_six_digits" and not pins.is_pin(pin)


@pytest.mark.parametrize("pin", ["000000", "111111", "999999",            # one digit
                                 "123456", "654321", "012345", "543210",  # runs
                                 "789012", "210987", "890123",            # runs that wrap
                                 "121212", "909090", "373737",            # pairs
                                 "123123", "907907",                      # the same three twice
                                 "112233", "998877", "440055"])           # three doubles
def test_easy_pins_are_refused(pin):
    assert pins.pin_problem(pin) == "too_easy"


def test_the_end_of_the_mobile_number_cannot_be_the_pin():
    assert pins.pin_problem("082488", "+639178082488") == "too_easy"
    assert pins.pin_problem("082488", "+639171234567") is None
    assert pins.pin_problem("082488", None) is None


def test_pins_are_stored_only_as_argon2_hashes():
    stored = pins.hash_pin("482913")
    assert stored.startswith("$argon2id$") and "482913" not in stored
    assert pins.hash_pin("482913") != stored  # salted
    assert pins.verify_pin(stored, "482913")
    assert not pins.verify_pin(stored, "482914")


@pytest.mark.parametrize("pin", ["", None, "abc", 482913, "4829130"])
def test_checking_a_pin_never_raises(pin):
    assert pins.verify_pin(pins.hash_pin("482913"), pin) is False
    assert pins.verify_pin(None, pin) is False and pins.verify_pin("not-a-hash", pin) is False


def test_only_six_digits_can_be_hashed():
    with pytest.raises(ValueError):
        pins.hash_pin("48291")
