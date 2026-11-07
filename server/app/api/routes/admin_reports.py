"""Admin dashboard, logs and reports (Phase 8)."""

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_admin
from app.config import get_settings
from app.models.user import User
from app.schemas.admin import DashboardRead
from app.services import (admin_service, report_pdf, report_service, report_summary,
                          system_settings_service)
from app.services.local_time import today_local
from app.services.report_service import LOGS_PER_PAGE, ReportError
from app.services.system_log_service import log_activity

router = APIRouter(prefix="/admin", tags=["admin"], route_class=DatabaseSafeRoute)
DEFAULT_REPORT_DAYS = 30


class LogItem(BaseModel):
    log_id: int
    activity_type: str
    user_name: str | None
    description: str | None
    log_date: str


class LogPage(BaseModel):
    items: list[LogItem]
    total: int
    page: int
    pages: int


class SummaryItemRead(BaseModel):
    label: str
    value: str


class ReportRead(BaseModel):
    type: str
    title: str
    columns: list[str]
    rows: list[list[str]]
    date_from: date
    date_to: date
    user_name: str | None
    note: str | None
    # Feature C: totals (counts and averages only, never message text).
    summary: list[SummaryItemRead] = []


def _summary(db, report, user_id) -> list:
    """Totals for a report; an empty list if they cannot be built (the report still works)."""
    try:
        return report_summary.summarize(db, report, user_id)
    except Exception:  # noqa: BLE001
        logging.getLogger("irisclick.reports").exception("Report summary failed")
        return []


def _fail(exc: ReportError):
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/dashboard", response_model=DashboardRead)
def dashboard(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return DashboardRead(**admin_service.dashboard(db))


@router.get("/logs", response_model=LogPage)
def logs(tab: str = "all", date_from: date | None = None, date_to: date | None = None,
         page: int = Query(1, ge=1), db: Session = Depends(get_db),
         _admin: User = Depends(require_admin)):
    try:
        rows, total = report_service.logs(db, tab, date_from, date_to, page)
    except ReportError as exc:
        _fail(exc)
    return LogPage(items=[LogItem(log_id=r.log_id, activity_type=r.activity_type,
                                  user_name=r.user_name, description=r.description,
                                  log_date=r.log_date.isoformat()) for r in rows],
                   total=total, page=page, pages=max(1, -(-total // LOGS_PER_PAGE)))


def _report(db, report_type, date_from, date_to, user_id, include_text):
    today = today_local()  # the Philippine date, also on Vercel's UTC servers
    date_to = date_to or today
    date_from = date_from or date_to - timedelta(days=DEFAULT_REPORT_DAYS - 1)
    try:
        return report_service.build(db, report_type, date_from, date_to, user_id,
                                    include_text and report_type == "communication")
    except ReportError as exc:
        _fail(exc)


@router.get("/reports/{report_type}", response_model=ReportRead)
def preview(report_type: str, date_from: date | None = None, date_to: date | None = None,
            user_id: int | None = None, include_text: bool = False,
            from_: date | None = Query(None, alias="from"), to: date | None = None,
            db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    # Feature C: ?from=&to= work as well as ?date_from=&date_to=.
    report = _report(db, report_type, date_from or from_, date_to or to, user_id, include_text)
    if include_text and report_type == "communication":
        log_activity("report_viewed", f"{admin.full_name} viewed the Communication report "
                     "with message text", admin.user_id, session=db)
    # Feature C: every generated report is logged (filters and row count, never content).
    log_activity("report_generated",
                 f"{admin.full_name} generated the {report.title} for {report.date_from} to "
                 f"{report.date_to} ({report.user_name or 'everyone'}, {len(report.rows)} rows)",
                 admin.user_id, session=db)
    db.commit()
    return ReportRead(**report.__dict__, summary=[
        SummaryItemRead(label=s.label, value=s.value) for s in _summary(db, report, user_id)])


@router.get("/reports/{report_type}/pdf")
def export_pdf(report_type: str, date_from: date | None = None, date_to: date | None = None,
               user_id: int | None = None, include_text: bool = False,
               from_: date | None = Query(None, alias="from"), to: date | None = None,
               db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    report = _report(db, report_type, date_from or from_, date_to or to, user_id, include_text)
    app_name = system_settings_service.app_name(db, get_settings())
    summary = [(s.label, s.value) for s in _summary(db, report, user_id)]
    pdf = report_pdf.render(report, app_name, admin.full_name, summary=summary)
    name = report_pdf.filename(report)
    detail = " with message text" if include_text and report_type == "communication" else ""
    log_activity("report_exported",
                 f"{admin.full_name} exported {name} ({len(report.rows)} rows{detail})",
                 admin.user_id, session=db)
    db.commit()
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "Access-Control-Expose-Headers": "Content-Disposition"})
