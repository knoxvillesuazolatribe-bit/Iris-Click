"""Imports every ORM model so Base.metadata knows all tables (Alembic, tests)."""

from app.models.accessibility_settings import AccessibilitySettings
from app.models.calibration_record import CalibrationRecord
from app.models.communication import CommunicationHistory
from app.models.screenshot import ScreenshotHistory
from app.models.sos import SosContact, SosHistory
from app.models.system_log import SystemLog
from app.models.user import User

__all__ = [
    "AccessibilitySettings",
    "CalibrationRecord",
    "CommunicationHistory",
    "ScreenshotHistory",
    "SosContact",
    "SosHistory",
    "SystemLog",
    "User",
]
