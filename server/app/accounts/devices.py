"""Computers on the hosted server: the ``devices`` table.

The website sends the computer ID it got from IrisClick Desktop in the header
``X-IrisClick-Device`` (never in a URL). Only its SHA-256 is stored or compared,
so the database cannot be used to pretend to be a computer.
"""

import hashlib

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.device_id import is_device_id
from app.models.account_models import Device
from app.models.timestamps import utc_now

DEVICE_HEADER = "X-IrisClick-Device"


def device_key_hash(device_id: str) -> str:
    return hashlib.sha256(device_id.encode("ascii")).hexdigest()


def find_device(db: Session, device_id: object) -> Device | None:
    """The computer with this ID, or None (also for a missing or malformed ID)."""
    if not is_device_id(device_id):
        return None
    return db.scalar(select(Device).where(Device.device_key_hash == device_key_hash(device_id)))


def remember_device(db: Session, device_id: object) -> Device | None:
    """Find the computer or add it, and note that it was just seen. None for a bad ID."""
    if not is_device_id(device_id):
        return None
    device = find_device(db, device_id)
    if device is None:
        device = Device(device_key_hash=device_key_hash(device_id))
        db.add(device)
        try:
            db.flush()
        except IntegrityError:  # another request added the same computer a moment ago
            db.rollback()
            device = find_device(db, device_id)
            if device is None:
                raise
    device.last_seen_at = utc_now()
    db.commit()
    return device
