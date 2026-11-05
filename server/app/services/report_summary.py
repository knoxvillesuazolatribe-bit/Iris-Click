"""Summary totals for admin reports (Feature C, Screens 35-36).

Built from the report's own rows, so the preview and the PDF always agree.
Only the SOS event count reads the database, with the same date and user
filters as the rows. Totals never include message text.
"""

from dataclasses import dataclass

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.sos import SosHistory
from app.services.report_service import Report, day_bounds


@dataclass(frozen=True)
class SummaryItem:
    label: str
    value: str


def _column(report: Report, name: str) -> list[str]:
    if name not in report.columns:
        return []
    index = report.columns.index(name)
    return [row[index] for row in report.rows if index < len(row)]


def _count(values: list[str], wanted: str) -> int:
    return sum(value == wanted for value in values)


def _int_total(values: list[str]) -> int:
    return sum(int(value) for value in values if value.strip().isdigit())


def _calibration(report: Report) -> list[SummaryItem]:
    statuses = _column(report, "Status")
    accuracies = [float(value.rstrip("%")) for value, status
                  in zip(_column(report, "Accuracy"), statuses)
                  if status == "Successful" and value.endswith("%")]
    average = f"{sum(accuracies) / len(accuracies):.2f}%" if accuracies else "No successful calibrations"
    return [
        SummaryItem("Calibrations", str(len(report.rows))),
        SummaryItem("Successful", str(_count(statuses, "Successful"))),
        SummaryItem("Failed", str(_count(statuses, "Failed"))),
        SummaryItem("Average accuracy (successful)", average),
    ]


def _communication(report: Report) -> list[SummaryItem]:
    if "Type" in report.columns:  # one row per message (message text included)
        types = _column(report, "Type")
        typed, spoken = _count(types, "Typed"), _count(types, "Spoken")
        people = len(set(_column(report, "User")))
    else:  # counts per person (default)
        typed = _int_total(_column(report, "Typed"))
        spoken = _int_total(_column(report, "Spoken"))
        people = len(report.rows)
    return [
        SummaryItem("Messages", str(typed + spoken)),
        SummaryItem("Typed (text to speech)", str(typed)),
        SummaryItem("Spoken (speech to text)", str(spoken)),
        SummaryItem("People", str(people)),
    ]


def _sos(db: Session, report: Report, user_id: int | None) -> list[SummaryItem]:
    start, end = day_bounds(report.date_from, report.date_to)
    query = select(func.count(distinct(SosHistory.activation_id))).where(
        SosHistory.date_sent >= start, SosHistory.date_sent < end)
    if user_id is not None:
        query = query.where(SosHistory.user_id == user_id)
    statuses = _column(report, "Status")
    return [
        SummaryItem("SOS events", str(db.scalar(query) or 0)),
        SummaryItem("Alerts", str(len(report.rows))),
        SummaryItem("Sent", str(_count(statuses, "Sent"))),
        SummaryItem("Failed", str(_count(statuses, "Failed"))),
        SummaryItem("Not sent yet", str(_count(statuses, "Pending"))),
    ]


def summarize(db: Session, report: Report, user_id: int | None = None) -> list[SummaryItem]:
    if report.type == "calibration":
        return _calibration(report)
    if report.type == "communication":
        return _communication(report)
    if report.type == "sos":
        return _sos(db, report, user_id)
    return []
