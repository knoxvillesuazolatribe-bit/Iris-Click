"""Owner's request: a contact with a mobile number AND an email gets both a text and an email.
Texts go to a fake sender; emails to the scripted fake email channel."""

from app.accounts import sms
from app.models.sos import SosContact
from app.services import sos_service
from app.services.sos_dispatcher import CHANNEL_EMAIL, CHANNEL_SMS
from tests.auth.conftest import api, fresh_throttle, make_user, profiles_dir  # noqa: F401
from tests.home.test_sos_routes import _activate, _add, _rows, ana, email  # noqa: F401


def contact(number=None, email_address=None):
    return SosContact(contact_name="X", contact_number=number, email_address=email_address)


def test_which_channels_each_contact_gets():
    assert sos_service.alert_channels(contact("09171234567", "a@b.co")) == [CHANNEL_SMS, CHANNEL_EMAIL]
    assert sos_service.alert_channels(contact("09171234567")) == [CHANNEL_SMS]
    assert sos_service.alert_channels(contact(email_address="a@b.co")) == [CHANNEL_EMAIL]
    # A landline cannot be texted: with an email, only the email; without one, still tried (and explained).
    assert sos_service.alert_channels(contact("(032) 340 1234", "a@b.co")) == [CHANNEL_EMAIL]
    assert sos_service.alert_channels(contact("(032) 340 1234")) == [CHANNEL_SMS]


def test_a_contact_with_both_gets_a_text_and_an_email(api, ana, email, test_database, monkeypatch):  # noqa: F811
    monkeypatch.setenv(sms.ONLY_TO_ENV, "")
    texts = []
    _add(api, name="Knox Cruz", number="0917 808 2488", email_address="knox@example.com", relationship="Brother")
    with sms.fake_sender(lambda number, text: texts.append((number, text))):
        view = _activate(api).json()

    assert (view["contacts_total"], view["contacts_notified"]) == (1, 1)
    assert (view["total"], view["sent"], view["failed"]) == (2, 2, 0)
    assert sorted(a["channel"] for a in view["alerts"]) == ["email", "sms"]
    assert texts[0][0] == "+639178082488" and texts[0][1].startswith("SOS: Ana Cruz needs help now.")
    assert email.sent[0][0] == "knox@example.com"
    assert len(_rows(test_database)) == 2


def test_a_contact_counts_as_notified_when_one_of_the_two_arrives(api, ana, email, test_database):  # noqa: F811
    _add(api, name="Knox Cruz", number="0917 808 2488", email_address="knox@example.com")
    view = _activate(api).json()  # tests never text for real: the SMS fails "not set up", the email is sent
    assert (view["total"], view["sent"], view["failed"]) == (2, 1, 1)
    assert (view["contacts_total"], view["contacts_notified"]) == (1, 1)
