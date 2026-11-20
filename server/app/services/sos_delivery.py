"""How an SOS alert reaches a contact: email over SMTP, or SMS through app/accounts/sms.py.

Team decision D8: email via SMTP with credentials in server/.env; SMS behind
a provider interface, which is a stub until a gateway (e.g. Semaphore) is
paid for. Every failure says why and whether trying again could help.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

import requests
from typing import Protocol

from app.config import Settings

logger = logging.getLogger("irisclick.sos")

EMAIL_NOT_SET_UP = ("Email is not set up on this computer, so this alert was not sent. "
                    "Ask your administrator to add the SMTP details.")
SMS_NOT_SET_UP = "SMS sending is not set up yet, so this contact was not texted. Add an email for them."
CANNOT_REACH = "Could not reach the email server. Check the internet connection."
BREVO_URL = "https://api.brevo.com/v3/smtp/email"
BREVO_KEY_REFUSED = "Brevo refused the API key. Check BREVO_API_KEY."
BREVO_BUSY = "Brevo could not send the email just now. Trying again."


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

    @property
    def uses_brevo(self) -> bool:
        return bool(self._s.brevo_api_key.get_secret_value().strip())

    def configured(self) -> bool:
        if self.uses_brevo:
            return bool(self.from_address)
        return bool(self._s.smtp_host and self.from_address)

    def send(self, to: str, subject: str, body: str) -> None:
        if not self.configured():
            raise DeliveryError(EMAIL_NOT_SET_UP, retryable=False)
        if self.uses_brevo:
            self._send_brevo(to, subject, body)
            return
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
            logger.warning("SOS email to the mail server failed at %s: %s: %s", self.step,
                           type(exc).__name__, exc)
            raise DeliveryError(f"{CANNOT_REACH} ({type(exc).__name__})", retryable=True) from exc

    def _send_brevo(self, to: str, subject: str, body: str) -> None:
        """Brevo's transactional email API. The key goes in a header, never in a URL or log."""
        name, address = parseaddr(self.from_address)
        sender = {"email": address, **({"name": name} if name else {})}
        payload = {"sender": sender, "to": [{"email": to}], "subject": subject, "textContent": body}
        headers = {"api-key": self._s.brevo_api_key.get_secret_value().strip(),
                   "accept": "application/json", "content-type": "application/json"}
        try:
            response = requests.post(BREVO_URL, json=payload, headers=headers,
                                     timeout=self._s.smtp_timeout_s)
        except requests.RequestException as exc:
            logger.warning("SOS email to Brevo failed: %s", type(exc).__name__)
            raise DeliveryError(f"{CANNOT_REACH} ({type(exc).__name__})", retryable=True) from exc
        if response.status_code in (200, 201, 202):
            return
        try:
            reason = str((response.json() or {}).get("message") or "").strip()
        except ValueError:
            reason = ""
        logger.warning("SOS email refused by Brevo: HTTP %s %s", response.status_code, reason)
        if response.status_code in (401, 403):
            raise DeliveryError(BREVO_KEY_REFUSED, retryable=False)
        if response.status_code == 429 or response.status_code >= 500:
            raise DeliveryError(BREVO_BUSY, retryable=True)
        raise DeliveryError(f"Brevo refused the email: {reason or response.status_code}.",
                            retryable=False)

    def _deliver(self, message: EmailMessage) -> None:
        """Connect, secure, sign in and send; ``self.step`` names the stage in progress."""
        s = self._s
        timeout = s.smtp_timeout_s
        self.step = "connect"
        if s.smtp_security == "ssl":
            client = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=timeout,
                                      context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=timeout)
        with client:
            if s.smtp_security == "starttls":
                self.step = "tls"
                client.starttls(context=ssl.create_default_context())
            if s.smtp_username:
                self.step = "login"
                client.login(s.smtp_username, s.smtp_password.get_secret_value())
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
