"""Report and SOS times are Philippine time, also on servers that run on UTC (Vercel)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.config import get_settings
from app.models.user import User
from app.services import local_time, report_pdf, report_service, sos_service

# The export in the bug report: 08:55 UTC is 4:55 PM in the Philippines.
EXPORTED = datetime(2026, 11, 7, 8, 55, tzinfo=UTC)


def test_stored_times_are_shown_in_philippine_time():
    assert local_time.to_local(EXPORTED).strftime("%I:%M %p") == "04:55 PM"
    assert local_time.to_local(EXPORTED.replace(tzinfo=None)).hour == 16  # SQLite hands back naive UTC
    assert report_service.local_text(EXPORTED) == "2026-11-07 16:55"
    assert local_time.to_local(EXPORTED).utcoffset() == timedelta(hours=8)


def test_report_days_are_philippine_days():
    start, end = report_service.day_bounds(date(2026, 11, 7), date(2026, 11, 7))
    assert start == datetime(2026, 11, 6, 16, 0, tzinfo=UTC)  # Nov 7, 00:00 in Manila
    assert end == datetime(2026, 11, 7, 16, 0, tzinfo=UTC)    # Nov 8, 00:00 in Manila


def test_the_export_time_and_file_name_use_philippine_time(monkeypatch):
    manila_evening = datetime(2026, 11, 7, 23, 30, tzinfo=local_time.display_zone())
    monkeypatch.setattr(report_pdf, "now_local", lambda: manila_evening)
    report = type("R", (), {"title": "SOS Report"})()
    assert report_pdf.filename(report) == "SOS_Report_2026-11-07.pdf"  # 15:30 UTC: Nov 7 in both
    after_midnight = datetime(2026, 11, 8, 0, 30, tzinfo=local_time.display_zone())  # Nov 7 16:30 UTC
    monkeypatch.setattr(report_pdf, "now_local", lambda: after_midnight)
    assert report_pdf.filename(report) == "SOS_Report_2026-11-08.pdf"


def test_sos_message_states_the_philippine_time():
    user = User(full_name="Ana Cruz", role="assistive_user", status="active")
    message = sos_service.build_message(user, None, EXPORTED)
    assert "November 07, 2026 at 04:55 PM" in message


def test_a_missing_time_zone_database_still_gives_philippine_time(monkeypatch):
    local_time._zone.cache_clear()
    settings = get_settings().model_copy(update={"display_timezone": "No/Such_Zone"})
    monkeypatch.setattr(local_time, "get_settings", lambda: settings)
    try:
        assert local_time.display_zone() is local_time.PHILIPPINE_TIME
        assert local_time.to_local(EXPORTED).strftime("%H:%M") == "16:55"
    finally:
        local_time._zone.cache_clear()


@pytest.mark.parametrize("utc_hour, manila_day", [(15, 7), (16, 8)])
def test_today_follows_the_philippine_date(monkeypatch, utc_hour, manila_day):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 7, utc_hour, 0, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(local_time, "datetime", Clock)
    assert local_time.today_local() == date(2026, 11, manila_day)
