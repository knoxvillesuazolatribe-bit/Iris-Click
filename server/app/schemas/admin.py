from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.schemas.accessibility import AccessibilitySettingsRead, AccessibilitySettingsWrite
from app.schemas.auth import AdminUserRead, Email, Name
from app.schemas.sos import SosContactRead


class DashboardRead(BaseModel):
    active_users: int
    active_users_week: int
    sos_events: int
    sos_events_week: int
    calibrations: int
    calibrations_week: int


class AdminUserRow(AdminUserRead):
    calibration_count: int
    latest_accuracy: Decimal | None
    last_calibrated_at: datetime | None


class AdminUserDetail(BaseModel):
    user: AdminUserRow
    sos_location: str | None
    settings: AccessibilitySettingsRead
    contacts: list[SosContactRead]


class AdminUserUpdate(BaseModel):
    full_name: Name
    address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    barangay: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None


class StatusUpdate(BaseModel):
    status: Literal["active", "inactive"]


class GlobalDefaultsRead(AccessibilitySettingsWrite):
    is_default: bool
    env_defaults: AccessibilitySettingsWrite


class EmailStatus(BaseModel):
    configured: bool
    host: str | None
    port: int
    security: str
    from_address: str | None


class SystemRead(BaseModel):
    app_name: str
    app_name_default: str
    email: EmailStatus
    sms_configured: bool


class AppNameUpdate(BaseModel):
    """Blank: back to the standard name."""
    app_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]


class TestEmailRequest(BaseModel):
    to: Email


class TestResult(BaseModel):
    sent: bool
    detail: str


class AppInfoRead(BaseModel):
    app_name: str
