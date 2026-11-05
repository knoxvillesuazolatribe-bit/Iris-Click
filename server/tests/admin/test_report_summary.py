"""Feature C: report totals, SOS message column, ?from/&to, logging, empty results."""

from datetime import date, timedelta

import pytest

from app.models.sos import SosHistory
from app.models.timestamps import utc_now
from app.services import report_pdf, report_summary

from tests.admin.conftest import add_calibration, logs
from tests.admin.test_admin_reports import data  # noqa: F401  (fixture)

TODAY = date.today()


def _summary(body):
    return {item["label"]: item["value"] for item in body["summary"]}


def test_calibration_totals(admin, data):
    totals = _summary(admin.get("/api/admin/reports/calibration").json())
    assert totals == {"Calibrations": "2", "Successful": "1", "Failed": "1",
                      "Average accuracy (successful)": "92.50%"}


def test_calibration_average_only_counts_successful(admin, make_user, test_database):
    ana = make_user("Ana Cruz")
    add_calibration(test_database, ana, file_id="a", accuracy="90.00")
    add_calibration(test_database, ana, file_id="b", accuracy="80.00")
    add_calibration(test_database, ana, status="Failed", accuracy="10.00")
    totals = _summary(admin.get("/api/admin/reports/calibration").json())
    assert totals["Average accuracy (successful)"] == "85.00%"


def test_communication_totals_default_and_with_text(admin, data):
    expected = {"Messages": "3", "Typed (text to speech)": "2", "Spoken (speech to text)": "1",
                "People": "2"}
    assert _summary(admin.get("/api/admin/reports/communication").json()) == expected
    with_text = admin.get("/api/admin/reports/communication?include_text=true").json()
    assert _summary(with_text) == expected
    # Totals never carry message text.
    assert "I need water" not in str(with_text["summary"])


def test_sos_totals_and_alert_message_column(admin, data, test_database):
    with test_database() as session:
        session.add(SosHistory(user_id=data["ana"], activation_id="a2", channel="email",
                               recipient="x@y.co", message_sent="EMERGENCY SOS: Ana needs help.\nMore",
                               status="pending"))
        session.commit()
    body = admin.get("/api/admin/reports/sos").json()
    assert body["columns"][-1] == "Alert message"
    assert body["columns"][:3] == ["Date", "User", "Contact"]  # existing columns unchanged
    assert "EMERGENCY SOS: Ana needs help." in [row[-1] for row in body["rows"]]
    assert "More" not in [row[-1] for row in body["rows"]]
    assert _summary(body) == {"SOS events": "2", "Alerts": "3", "Sent": "1", "Failed": "1",
                              "Not sent yet": "1"}


def test_sos_events_follow_the_user_filter(admin, data):
    body = admin.get(f"/api/admin/reports/sos?user_id={data['ben']}").json()
    assert _summary(body)["SOS events"] == "0" and body["rows"] == []


def test_from_and_to_work_like_date_from_and_date_to(admin, data):
    old = (TODAY - timedelta(days=100)).isoformat()
    a = admin.get(f"/api/admin/reports/calibration?from={old}&to={TODAY}").json()
    b = admin.get(f"/api/admin/reports/calibration?date_from={old}&date_to={TODAY}").json()
    assert a["date_from"] == b["date_from"] == old
    assert len(a["rows"]) == len(b["rows"]) == 3  # includes the 90-day-old calibration


def test_every_generated_report_is_logged_without_content(admin, data, test_database):
    admin.get("/api/admin/reports/communication?include_text=true")
    admin.get("/api/admin/reports/sos")
    generated = logs(test_database, "report_generated")
    assert len(generated) == 2
    assert "Communication Report" in generated[0].activity_description
    assert "SOS Report" in generated[1].activity_description
    for entry in generated:
        assert "I need water" not in entry.activity_description
        assert "EMERGENCY" not in entry.activity_description


def test_empty_result_says_no_records_and_still_exports(admin, monkeypatch):
    body = admin.get("/api/admin/reports/sos").json()
    assert body["rows"] == []
    assert _summary(body)["Alerts"] == "0"
    texts = []
    real = report_pdf.Paragraph

    def capture(text, *args, **kwargs):
        texts.append(text)
        return real(text, *args, **kwargs)

    monkeypatch.setattr(report_pdf, "Paragraph", capture)
    response = admin.get("/api/admin/reports/sos/pdf")
    assert response.content.startswith(b"%PDF")
    assert report_pdf.NO_RECORDS in texts
    assert "Alert message" in texts  # the empty table still has its header


def test_pdf_includes_the_summary(admin, data, monkeypatch):
    texts = []
    real = report_pdf.Paragraph
    monkeypatch.setattr(report_pdf, "Paragraph",
                        lambda text, *a, **k: texts.append(text) or real(text, *a, **k))
    admin.get("/api/admin/reports/calibration/pdf")
    assert "Average accuracy (successful)" in texts and "92.50%" in texts


def test_a_broken_summary_never_breaks_the_report(admin, data, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("summary bug")

    monkeypatch.setattr(report_summary, "summarize", broken)
    body = admin.get("/api/admin/reports/calibration").json()
    assert body["summary"] == [] and len(body["rows"]) == 2
    assert admin.get("/api/admin/reports/calibration/pdf").content.startswith(b"%PDF")


def test_reports_stay_admin_only(api, make_user, env):
    assert api.get("/api/admin/reports/calibration?from=2026-01-01").status_code == 401
    assert api.post("/api/assistive/select", json={"user_id": make_user("Ana Cruz")}).status_code == 200
    assert api.get("/api/admin/reports/sos/pdf").status_code == 403
