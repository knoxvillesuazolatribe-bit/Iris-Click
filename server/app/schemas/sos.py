from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
PHONE_PATTERN = r"^\+?[0-9][0-9 -]{5,18}[0-9]$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


class SosContactWrite(BaseModel):
    contact_name: Name
    contact_number: Annotated[str, StringConstraints(max_length=30, pattern=PHONE_PATTERN)] | None = None
    email_address: Annotated[str, StringConstraints(max_length=255, pattern=EMAIL_PATTERN,
                                                    to_lower=True)] | None = None
    relationship: Annotated[str, StringConstraints(max_length=50)] | None = None

    @field_validator("contact_number", "email_address", "relationship", mode="before")
    @classmethod
    def blank_is_none(cls, value):
        return _blank_to_none(value)

    @model_validator(mode="after")
    def reachable(self):
        if not self.contact_number and not self.email_address:
            raise ValueError("Add a mobile number or an email so SOS can reach this contact.")
        return self


class SosContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    contact_id: int
    contact_name: str
    contact_number: str | None
    email_address: str | None
    relationship: str | None


class SosOverviewRead(BaseModel):
    contacts: list[SosContactRead]
    location_text: str | None
    email_configured: bool
    sms_configured: bool


class SosActivateRequest(BaseModel):
    activation_id: UUID


class AlertStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    contact_name: str
    relationship: str | None
    channel: Literal["email", "sms"]
    recipient: str | None
    status: Literal["pending", "sent", "failed", "cancelled"]
    detail: str | None


class SosActivationRead(BaseModel):
    activation_id: str
    activated_at: datetime
    location_text: str | None
    total: int
    sent: int
    failed: int
    pending: int
    alerts: list[AlertStatusRead]
