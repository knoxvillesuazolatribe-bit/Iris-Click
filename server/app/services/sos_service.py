"""Emergency SOS for the signed-in assistive user: contacts, activation, status.

Never fakes success: rows start "pending" and only the dispatcher marks
them sent or failed after a real delivery attempt.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.sos import SOS_FAILED, SOS_PENDING, SOS_SENT, SosContact, SosHistory
from app.models.timestamps import as_utc, utc_now
from app.models.user import User
from app.services.sos_delivery import EmailSender
from app.services.sos_dispatcher import CHANNEL_EMAIL, CHANNEL_SMS, dispatcher
from app.services.system_log_service import log_activity

MAX_CONTACTS = 10
CITY = "Lapu-Lapu City"
# A second press within this window shows the alert already being sent.
DUPLICATE_WINDOW = timedelta(seconds=60)
# Pending this long with no sender working on it: the server restarted mid-retry.
STALE_PENDING = timedelta(minutes=5)
STOPPED_BY_RESTART = "Not sent: retrying stopped because the IrisClick server restarted."
NO_CONTACTS = "No emergency contacts yet. Ask a caregiver to add them first."


class SosError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# --- Contacts ----------------------------------------------------------------

def list_contacts(db: Session, user: User) -> list[SosContact]:
    return list(db.scalars(select(SosContact).where(SosContact.user_id == user.user_id)
                           .order_by(SosContact.contact_name, SosContact.contact_id)))


def _own_contact(db: Session, user: User, contact_id: int) -> SosContact:
    contact = db.get(SosContact, contact_id)
    if contact is None or contact.user_id != user.user_id:
        raise SosError(404, "That contact was not found.")
    return contact


def add_contact(db: Session, user: User, fields: dict) -> SosContact:
    if len(list_contacts(db, user)) >= MAX_CONTACTS:
        raise SosError(409, f"You can have up to {MAX_CONTACTS} emergency contacts.")
    contact = SosContact(user_id=user.user_id, **fields)
    db.add(contact)
    db.flush()
    log_activity("sos_contact_added", f"Emergency contact added for {user.full_name}",
                 user.user_id, session=db)
    db.commit()
    db.refresh(contact)
    return contact


def update_contact(db: Session, user: User, contact_id: int, fields: dict) -> SosContact:
    contact = _own_contact(db, user, contact_id)
    for key, value in fields.items():
        setattr(contact, key, value)
    log_activity("sos_contact_updated", f"Emergency contact changed for {user.full_name}",
                 user.user_id, session=db)
    db.commit()
    db.refresh(contact)
    return contact


def delete_contact(db: Session, user: User, contact_id: int) -> None:
    db.delete(_own_contact(db, user, contact_id))
    log_activity("sos_contact_deleted", f"Emergency contact deleted for {user.full_name}",
                 user.user_id, session=db)
    db.commit()


# --- Location and message ----------------------------------------------------

def location_text(user: User) -> str | None:
    """The address and barangay on file, or None when both are blank."""
    parts = []
    if user.address and user.address.strip():
        parts.append(user.address.strip())
    if user.barangay and user.barangay.strip():
        barangay = user.barangay.strip()
        parts.append(barangay if barangay.lower().startswith(("barangay", "brgy")) else f"Barangay {barangay}")
    if not parts:
        return None
    return ", ".join([*parts, CITY])


def build_message(user: User, location: str | None, when: datetime) -> str:
    time_text = when.astimezone().strftime("%B %d, %Y at %I:%M %p")
    return "\n".join([
        f"EMERGENCY SOS: {user.full_name} needs help.",
        "",
        f"{user.full_name} pressed the SOS button in IrisClick and may need help right now.",
        f"Location: {location or 'No address on file. Please call them to find out where they are.'}",
        f"Time: {time_text}",
        "",
        "Please call them or go to them as soon as you can.",
        "",
        "Sent by IrisClick (PDAO Lapu-Lapu City), a hands-free eye-gaze tool.",
    ])


# --- Activation --------------------------------------------------------------

def overview(db: Session, user: User) -> dict:
    return {"contacts": list_contacts(db, user), "location_text": location_text(user),
            "email_configured": EmailSender(get_settings()).configured(),
            "sms_configured": False}


def activate(db: Session, user: User, activation_id: str) -> str:
    """Creates one pending row per contact and starts sending; returns the activation id.

    The same id twice, or any press within DUPLICATE_WINDOW, returns the
    activation already in progress instead of alerting everyone again.
    """
    same = db.scalar(select(SosHistory.activation_id)
                     .where(SosHistory.activation_id == activation_id).limit(1))
    if same is not None:
        if not _belongs_to(db, user, activation_id):
            raise SosError(409, "Please press SOS again.")
        return activation_id
    # A recent SOS that is sending or sent wins; one that fully failed may be retried.
    since = utc_now() - DUPLICATE_WINDOW
    recent = db.scalar(select(SosHistory.activation_id)
                       .where(SosHistory.user_id == user.user_id, SosHistory.date_sent >= since,
                              SosHistory.status.in_((SOS_PENDING, SOS_SENT)))
                       .order_by(SosHistory.date_sent.desc()).limit(1))
    if recent is not None:
        return recent

    contacts = list_contacts(db, user)
    if not contacts:
        raise SosError(409, NO_CONTACTS)
    now = utc_now()
    location = location_text(user)
    message = build_message(user, location, now)
    rows = []
    for contact in contacts:
        channel = CHANNEL_EMAIL if contact.email_address else CHANNEL_SMS
        rows.append(SosHistory(
            user_id=user.user_id, contact_id=contact.contact_id, activation_id=activation_id,
            channel=channel,
            recipient=contact.email_address if channel == CHANNEL_EMAIL else contact.contact_number,
            message_sent=message, location_text=location, status=SOS_PENDING, date_sent=now))
    db.add_all(rows)
    db.flush()
    row_ids = [r.sos_id for r in rows]
    log_activity("sos_activated",
                 f"{user.full_name} activated SOS: alerting {len(rows)} contact(s)",
                 user.user_id, session=db)
    db.commit()
    dispatcher.submit(activation_id, row_ids, user.user_id, user.full_name)
    return activation_id


def _belongs_to(db: Session, user: User, activation_id: str) -> bool:
    owner = db.scalar(select(SosHistory.user_id)
                      .where(SosHistory.activation_id == activation_id).limit(1))
    return owner == user.user_id


@dataclass(frozen=True)
class AlertStatus:
    contact_name: str
    relationship: str | None
    channel: str
    recipient: str | None
    status: str
    detail: str | None


def activation_view(db: Session, user: User, activation_id: str) -> dict:
    # The sender updates these rows from its own session; always read them fresh.
    rows = list(db.scalars(select(SosHistory)
                           .where(SosHistory.activation_id == activation_id,
                                  SosHistory.user_id == user.user_id)
                           .order_by(SosHistory.sos_id)
                           .execution_options(populate_existing=True)))
    if not rows:
        raise SosError(404, "That SOS was not found.")
    now = utc_now()
    changed = False
    for row in rows:
        if (row.status == SOS_PENDING and not dispatcher.is_active(row.sos_id)
                and now - as_utc(row.date_sent) > STALE_PENDING):
            row.status, row.error_detail = SOS_FAILED, STOPPED_BY_RESTART
            changed = True
    if changed:
        db.commit()

    contacts = {c.contact_id: c for c in list_contacts(db, user)}
    alerts = []
    for row in rows:
        contact = contacts.get(row.contact_id)
        alerts.append(AlertStatus(
            contact_name=contact.contact_name if contact else (row.recipient or "Removed contact"),
            relationship=contact.relationship if contact else None,
            channel=row.channel or CHANNEL_EMAIL, recipient=row.recipient, status=row.status,
            detail=row.error_detail))
    return {
        "activation_id": activation_id,
        "activated_at": min(as_utc(r.date_sent) for r in rows),
        "location_text": rows[0].location_text,
        "total": len(rows),
        "sent": sum(r.status == SOS_SENT for r in rows),
        "failed": sum(r.status == SOS_FAILED for r in rows),
        "pending": sum(r.status == SOS_PENDING for r in rows),
        "alerts": alerts,
    }


def cancel(db: Session, user: User) -> None:
    """The countdown was cancelled: nothing was sent (recorded in system_logs only)."""
    log_activity("sos_cancelled", f"{user.full_name} cancelled SOS before it was sent",
                 user.user_id, session=db)
    db.commit()
