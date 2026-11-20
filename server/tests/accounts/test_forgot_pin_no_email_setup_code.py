"""Forgot PIN never sends email: the PDAO setup-code reset runs end to end with email trapped."""

from tests.accounts.test_setup_codes import api, secret  # noqa: F401 - fixtures
from tests.accounts.test_setup_codes import (
    test_a_forgotten_pin_is_replaced_and_the_old_pin_stops_working as reset_by_setup_code,
)
from tests.email_trap import email_attempts  # noqa: F401 - fixture


def test_forgot_pin_by_pdao_setup_code_sends_no_email(test_database, api, email_attempts):  # noqa: F811
    reset_by_setup_code(test_database, api)
    assert email_attempts == []
