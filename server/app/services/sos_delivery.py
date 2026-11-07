"""How an SOS alert reaches a contact: email over SMTP, or SMS (not set up yet).

Team decision D8: email via SMTP with credentials in server/.env; SMS behind
a provider interface, which is a stub until a gateway (e.g. Semaphore) is
paid for. Every failure says why and whether trying again could help.
"""

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Protocol

from app.config import Settings

EMAIL_NOT_SET_UP = ("Email is not set up on this computer, so this alert was not sent. "
                    "Ask your administrator to add the SMTP details.")
SMS_NOT_SET_UP = "SMS sending is not set up yet, so this contact was not texted. Add an email for them."
CANNOT_REACH = "Could not reach the email server. Check the internet connection."


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
            raise DeliveryError(CANNOT_REACH, retryable=True) from exc

    def _deliver(self, message: EmailMessage) -> None:
        s = self._s
        timeout = s.smtp_timeout_s
        if s.smtp_security == "ssl":
            client = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=timeout,
                                      context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=timeout)
        with client:
            if s.smtp_security == "starttls":
                client.starttls(context=ssl.create_default_context())
            if s.smtp_username:
                client.login(s.smtp_username, s.smtp_password.get_secret_value())
            client.send_message(message)


class NotConfiguredSms:
    """SMS provider placeholder: always fails, plainly."""

    def configured(self) -> bool:
        return False

    def send(self, to: str, subject: str, body: str) -> None:
        raise DeliveryError(SMS_NOT_SET_UP, retryable=False)
