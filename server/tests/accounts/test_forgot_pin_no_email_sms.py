"""Forgot PIN never sends email: the text-code reset runs end to end with email trapped."""

from tests.accounts.test_forgot_pin_sms import (  # noqa: F401 - fixtures
    api,
    own_file,
    signing_secret,
    texts,
)
from tests.accounts.test_forgot_pin_sms import (
    test_forgot_pin_by_text_sets_a_new_pin_and_ends_other_sessions as reset_by_text,
)
from tests.email_trap import email_attempts  # noqa: F401 - fixture


def test_forgot_pin_by_text_sends_no_email(api, texts, test_database, email_attempts):  # noqa: F811
    reset_by_text(api, texts, test_database)
    assert email_attempts == []
    assert texts  # the code went by text, not email
