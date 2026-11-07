"""Dates and times as people in the Philippines read them.

Report PDFs and SOS messages used the server's own clock zone. That is
Philippine time on the IrisClick PC but UTC on Vercel, so an export at
4:55 PM said 08:55 AM. Everything people read goes through here instead
(settings.display_timezone, default Asia/Manila).
"""

from datetime import date, datetime, timedelta, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import get_settings
from app.models.timestamps import as_utc

# The Philippines has no daylight saving time, so this is exact if the time zone
# database is missing (Windows without the tzdata package, slim Linux images).
PHILIPPINE_TIME = timezone(timedelta(hours=8), "PHT")


@lru_cache
def _zone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return PHILIPPINE_TIME


def display_zone() -> tzinfo:
    return _zone(get_settings().display_timezone)


def now_local() -> datetime:
    return datetime.now(display_zone())


def today_local() -> date:
    return now_local().date()


def to_local(value: datetime) -> datetime:
    """A stored time (UTC, or naive UTC from SQLite) in the display time zone."""
    return as_utc(value).astimezone(display_zone())


def day_start(day: date) -> datetime:
    """Midnight at the start of ``day`` in the display time zone."""
    return datetime.combine(day, datetime.min.time(), tzinfo=display_zone())
