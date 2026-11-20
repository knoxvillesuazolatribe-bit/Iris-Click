"""How an SOS alert reaches a contact: email over SMTP, or SMS through app/accounts/sms.py.

Team decision D8: email via SMTP with credentials in server/.env; SMS behind
a provider interface, which is a stub until a gateway (e.g. Semaphore) is
paid for. Every failure says why and whether trying again could help.
"""

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Protocol

from app.config import Settings

logger = logging.getLogger("irisclick.sos")

EMAIL_NOT_SET_UP = ("Email is not set up on this computer, so this alert was not sent. "
                    "Ask your administrator to add the SMTP details.")
SMS_NOT_SET_UP = "SMS sending is not set up yet, so this contact was not texted. Add an email for them."
CANNOT_REACH = "Could not reach the email server. Check the internet connection."
# Online, introduce the server to the mail server by the site's name instead of whatever
# name the cloud machine has; on a PC smtplib's own default (the computer's name) is kept.
ONLINE_HELLO_NAME = "irisclick.vercel.app"


def secret_shape(value: str) -> str:
    """How a pasted secret looks, never what it is: length and stray spaces or line breaks."""
    notes = [f"{len(value)} characters"]
    if value != value.strip():
        notes.append("spaces or line breaks at the ends")
    if " " in value.strip():
        notes.append("spaces inside")
    return ", ".join(notes)


class DeliveryError(Exception):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class Channel(Protocol):
    def configured(self) -> bool: ...
    def send(self, to: str, subject: str, body: str) -> None: ...


class EmailSender:
    def __init__(self, settings: Settings):
        self._s = settings

    @property
    def from_address(self) -> str:
        return self._s.smtp_from or self._s.smtp_username

    def configured(self) -> bool:
        return bool(self._s.smtp_host and self.from_address)

    def send(self, to: str, subject: str, body: str) -> None:
        if not self.configured():
            raise DeliveryError(EMAIL_NOT_SET_UP, retryable=False)
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.from_address
        message["To"] = to
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = make_msgid(domain="irisclick.local")
        message.set_content(body)
        self.step = "connect"
        try:
            self._deliver(message)
        except smtplib.SMTPAuthenticationError as exc:
            raise DeliveryError("The email account's username or app password was refused. "
                                "Check SMTP_USERNAME and SMTP_PASSWORD.", retryable=False) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise DeliveryError(f"The mail server refused the address {to}.",
                                retryable=False) from exc
        except smtplib.SMTPSenderRefused as exc:
            raise DeliveryError("The mail server refused the sending address (SMTP_FROM).",
                                retryable=False) from exc
        except (smtplib.SMTPException, OSError) as exc:
            # The kind of failure (timeout, unknown host, Gmail hanging up...) is what tells
            # an admin what to fix; it never contains the password.
            # The step (connect, tls, login, send) shows whether the server refused the
            # connection itself or a later stage.
            logger.warning("SOS email to the mail server failed at %s: %s: %s (hello reply %s; "
                           "username %s; password %s)", self.step, type(exc).__name__, exc,
                           getattr(self, "hello_reply", None),
                           secret_shape(self._s.smtp_username),
                           secret_shape(self._s.smtp_password.get_secret_value()))
            raise DeliveryError(f"{CANNOT_REACH} ({type(exc).__name__})", retryable=True) from exc

    def _deliver(self, message: EmailMessage) -> None:
        """Connect, secure, sign in and send; ``self.step`` names the stage in progress."""
        s = self._s
        timeout = s.smtp_timeout_s
        self.step = "connect"
        self.hello_reply = None
        hello_name = ONLINE_HELLO_NAME if os.environ.get("VERCEL") else None
        if s.smtp_security == "ssl":
            client = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=timeout,
                                      context=ssl.create_default_context(), local_hostname=hello_name)
        else:
            client = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=timeout, local_hostname=hello_name)
        with client:
            self.step = "hello"
            self.hello_reply = client.ehlo()[0]
            if s.smtp_security == "starttls":
                self.step = "tls"
                client.starttls(context=ssl.create_default_context())
                self.step = "hello"
                self.hello_reply = client.ehlo()[0]
            username = s.smtp_username.strip()
            if username:
                self.step = "login"
                # Pasted values can carry an invisible space or line break; Gmail addresses
                # and app passwords never have spaces at their ends.
                client.login(username, s.smtp_password.get_secret_value().strip())
            self.step = "send"
            client.send_message(message)


# Adviser/owner: SOS texts go through the same sender as the sign-in codes (app/accounts/sms.py).
SMS_REFUSED = {
    "not_configured": (SMS_NOT_SET_UP, False),
    "not_allowed": ("This contact's number can't be texted: it is not a mobile number, or SMS is still "
                    "in testing mode (SMS_ONLY_TO). Add an email for them.", False),
    "no_sender_name": ("The SMS gateway has no approved sender name yet, so this contact was not texted.", False),
    "failed": ("The text could not be sent. Trying again.", True),
}


class AccountsSms:
    """SOS by SMS: the iProg sender of app/accounts/sms.py. Temporary failures are retried."""

    def configured(self) -> bool:
        from app.accounts import sms
        return sms.configured()

    def send(self, to: str, subject: str, body: str) -> None:
        from app.accounts import sms
        try:
            sms.send(to, body)
        except sms.SmsError as exc:
            message, retryable = SMS_REFUSED.get(exc.reason, SMS_REFUSED["failed"])
            raise DeliveryError(message, retryable=retryable) from exc


class NotConfiguredSms:
    """SMS provider placeholder: always fails, plainly."""

    def configured(self) -> bool:
        return False

    def send(self, to: str, subject: str, body: str) -> None:
        raise DeliveryError(SMS_NOT_SET_UP, retryable=False)
