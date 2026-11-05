"""Admin logs and reports (Phase 8): the rows behind both the preview and the PDF.

Dates are whole local days; times are shown in this computer's time zone.
The Communication report gives counts per person unless the admin asks for
the message text, which may be private (that request is logged).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.calibration_record import CalibrationRecord
from app.models.communication import MODE_TEXT_TO_SPEECH, CommunicationHistory
from app.models.sos import SosContact, SosHistory
from app.models.system_log import SystemLog
from app.models.timestamps import as_utc
from app.models.user import User

LOG_TABS = ("all", "calibration", "sos", "communication", "screenshot")
LOGS_PER_PAGE = 50
REPORT_TYPES = {"calibration": "Calibration", "communication": "Communication", "sos": "SOS"}
MAX_RANGE_DAYS = 366


class ReportError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def day_bounds(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    """UTC instants for the start of ``date_from`` and the end of ``date_to`` (local days)."""
    if date_from and date_to and date_to < date_from:
        raise ReportError(422, "The end date is before the start date.")
    start = (datetime.combine(date_from, time.min).astimezone().astimezone(UTC)
             if date_from else None)
    end = (datetime.combine(date_to + timedelta(days=1), time.min).astimezone().astimezone(UTC)
           if date_to else None)
    return start, end


def local_text(value: datetime | None) -> str:
    return as_utc(value).astimezone().strftime("%Y-%m-%d %H:%M") if value else ""


# --- Logs ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class LogRow:
    log_id: int
    activity_type: str
    user_name: str | None
    description: str | None
    log_date: datetime


def logs(db: Session, tab: str, date_from: date | None, date_to: date | None,
         page: int) -> tuple[list[LogRow], int]:
    if tab not in LOG_TABS:
        raise ReportError(422, f"Unknown tab {tab!r}.")
    start, end = day_bounds(date_from, date_to)
    query = select(SystemLog, User.full_name).outerjoin(User, User.user_id == SystemLog.user_id)
    if tab != "all":
        query = query.where(SystemLog.activity_type.like(f"{tab}%"))
    if start:
        query = query.where(SystemLog.log_date >= start)
    if end:
        query = query.where(SystemLog.log_date < end)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(SystemLog.log_date.desc(), SystemLog.log_id.desc())
                      .limit(LOGS_PER_PAGE).offset((max(page, 1) - 1) * LOGS_PER_PAGE)).all()
    return [LogRow(log.log_id, log.activity_type, name, log.activity_description,
                   as_utc(log.log_date)) for log, name in rows], total


# --- Reports -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Report:
    type: str
    title: str
    columns: list[str]
    rows: list[list[str]]
    date_from: date
    date_to: date
    user_name: str | None
    note: str | None = None


def _window(column, start, end):
    return [column >= start, column < end]


def _user_filter(column, user_id):
    return [column == user_id] if user_id is not None else []


def build(db: Session, report_type: str, date_from: date, date_to: date,
          user_id: int | None = None, include_text: bool = False) -> Report:
    if report_type not in REPORT_TYPES:
        raise ReportError(404, "That report does not exist.")
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        raise ReportError(422, "Choose a period of one year or less.")
    start, end = day_bounds(date_from, date_to)
    user_name = None
    if user_id is not None:
        user = db.get(User, user_id)
        if user is None:
            raise ReportError(404, "That user was not found.")
        user_name = user.full_name
    builder = {"calibration": _calibration, "communication": _communication, "sos": _sos}
    columns, rows, note = builder[report_type](db, start, end, user_id, include_text)
    return Report(report_type, f"{REPORT_TYPES[report_type]} Report", columns, rows,
                  date_from, date_to, user_name, note)


def _calibration(db, start, end, user_id, _include_text):
    query = (select(CalibrationRecord, User.full_name)
             .outerjoin(User, User.user_id == CalibrationRecord.user_id)
             .where(*_window(CalibrationRecord.calibration_date, start, end),
                    *_user_filter(CalibrationRecord.user_id, user_id))
             .order_by(CalibrationRecord.calibration_date.desc()))
    rows = [[local_text(c.calibration_date), name or "Not signed in", c.profile_name or "",
             f"{c.accuracy_score:.2f}%" if c.accuracy_score is not None else "",
             c.status, c.failure_reason or ""]
            for c, name in db.execute(query).all()]
    return ["Date", "User", "Profile", "Accuracy", "Status", "Failure reason"], rows, None


def _communication(db, start, end, user_id, include_text):
    filters = [*_window(CommunicationHistory.date_created, start, end),
               *_user_filter(CommunicationHistory.user_id, user_id)]
    if include_text:
        query = (select(CommunicationHistory, User.full_name)
                 .join(User, User.user_id == CommunicationHistory.user_id)
                 .where(*filters).order_by(CommunicationHistory.date_created.desc()))
        rows = [[local_text(m.date_created), name,
                 "Typed" if m.mode == MODE_TEXT_TO_SPEECH else "Spoken", m.message]
                for m, name in db.execute(query).all()]
        return (["Date", "User", "Type", "Message"], rows,
                "Includes message text, which may be private.")
    typed = func.sum(case((CommunicationHistory.mode == MODE_TEXT_TO_SPEECH, 1), else_=0))
    query = (select(User.full_name, typed, func.count(), func.max(CommunicationHistory.date_created))
             .join(User, User.user_id == CommunicationHistory.user_id)
             .where(*filters).group_by(User.user_id, User.full_name).order_by(User.full_name))
    rows = [[name, str(int(typed_count or 0)), str(total - int(typed_count or 0)), str(total),
             local_text(last)] for name, typed_count, total, last in db.execute(query).all()]
    return (["User", "Typed", "Spoken", "Total messages", "Last used"], rows,
            "Counts only. Message text is left out because it may be private.")


def _sos(db, start, end, user_id, _include_text):
    query = (select(SosHistory, User.full_name, SosContact.contact_name)
             .join(User, User.user_id == SosHistory.user_id)
             .outerjoin(SosContact, SosContact.contact_id == SosHistory.contact_id)
             .where(*_window(SosHistory.date_sent, start, end),
                    *_user_filter(SosHistory.user_id, user_id))
             .order_by(SosHistory.date_sent.desc(), SosHistory.sos_id))
    # Feature C: the alert's first line is added as a last column (existing columns keep
    # their positions); SOS text is never filtered or shortened anywhere else.
    rows = [[local_text(s.date_sent), name, contact or "(removed contact)",
             "Email" if s.channel == "email" else "SMS", s.recipient or "",
             s.status.capitalize(), s.error_detail or "", s.location_text or "No address on file",
             (s.message_sent or "").splitlines()[0] if s.message_sent else ""]
            for s, name, contact in db.execute(query).all()]
    return (["Date", "User", "Contact", "Channel", "Sent to", "Status", "Problem", "Location",
             "Alert message"], rows, None)
