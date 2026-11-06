"""Imports every ORM model so Base.metadata knows all tables (Alembic, tests)."""

from app.models.accessibility_settings import AccessibilitySettings
from app.models.calibration_record import CalibrationRecord
from app.models.communication import CommunicationHistory
from app.models.screenshot import ScreenshotHistory
from app.models.sos import SosContact, SosHistory
from app.models.system_log import SystemLog
from app.models.system_settings import SystemSettings
from app.models.user import User
from app.models.user_app_shortcut import UserAppShortcut  # extension: custom Apps
from app.models.word_filter import FilteredWord, WordFilterSettings  # extension: word filter
from app.models.user_speech_settings import UserSpeechSettings  # extension: speech language
from app.models.user_session import UserSession

__all__ = [
    "AccessibilitySettings",
    "CalibrationRecord",
    "CommunicationHistory",
    "ScreenshotHistory",
    "SosContact",
    "SosHistory",
    "SystemLog",
    "SystemSettings",
    "User",
    "UserAppShortcut",
    "UserSession",
    "FilteredWord",
    "WordFilterSettings",
    "UserSpeechSettings",
]
