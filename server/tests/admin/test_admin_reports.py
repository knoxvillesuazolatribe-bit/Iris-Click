"""Admin logs, report previews and PDF exports (Phase 8)."""

import re
from datetime import date, datetime, timedelta

import pytest

from app.models.communication import CommunicationHistory
from app.models.sos import SosContact, SosHistory
from app.models.system_log import SystemLog
from app.models.timestamps import utc_now
from app.services import report_pdf, report_service

from tests.admin.conftest import add_calibration, logs

TODAY = date.today()


def _log(factory, kind, days_ago=0, user_id=None, text="x"):
    with factory() as session:
        session.add(SystemLog(activity_type=kind, activity_description=text, user_id=user_id,
                              log_date=utc_now() - timedelta(days=days_ago)))
        session.commit()


# --- Logs -----------------------------------------------------------------------------------

def test_logs_newest_first_with_user_names(admin, make_user, test_database):
    ana = make_user("Ana Cruz")
    _log(test_database, "calibration", days_ago=2, user_id=ana, text="older")
    _log(test_database, "sos_activated", user_id=ana, text="newer")
    items = admin.get("/api/admin/logs").json()["items"]
    mine = [i for i in items if i["description"] in ("older", "newer")]
    assert [i["description"] for i in mine] == ["newer", "older"]
    assert mine[0]["user_name"] == "Ana Cruz"


@pytest.mark.parametrize(("tab", "expected"), [
    ("calibration", {"calibration", "calibration_failed"}), ("sos", {"sos_activated"}),
    ("communication", {"communication_sent"}), ("screenshot", {"screenshot"}),
])
def test_log_tabs(admin, test_database, tab, expected):
    for kind in ("calibration", "calibration_failed", "sos_activated", "communication_sent",
                 "screenshot", "login"):
        _log(test_database, kind)
    kinds = {i["activity_type"] for i in admin.get(f"/api/admin/logs?tab={tab}").json()["items"]}
    assert kinds == expected


def test_log_date_filter_and_paging(admin, test_database):
    for _ in range(60):
        _log(test_database, "screenshot")
    _log(test_database, "screenshot", days_ago=10, text="old one")
    page1 = admin.get("/api/admin/logs?tab=screenshot").json()
    assert (page1["total"], page1["pages"], len(page1["items"])) == (61, 2, 50)
    assert len(admin.get("/api/admin/logs?tab=screenshot&page=2").json()["items"]) == 11
    since = (TODAY - timedelta(days=1)).isoformat()
    assert admin.get(f"/api/admin/logs?tab=screenshot&date_from={since}").json()["total"] == 60
    old_day = (TODAY - timedelta(days=10)).isoformat()
    only_old = admin.get(f"/api/admin/logs?date_from={old_day}&date_to={old_day}").json()
    assert [i["description"] for i in only_old["items"]] == ["old one"]


def test_bad_log_requests(admin):
    assert admin.get("/api/admin/logs?tab=secrets").status_code == 422
    assert admin.get(f"/api/admin/logs?date_from={TODAY}&date_to={TODAY - timedelta(days=1)}"
                     ).status_code == 422


# --- Reports --------------------------------------------------------------------------------

@pytest.fixture
def data(make_user, test_database):
    ana, ben = make_user("Ana Cruz"), make_user("Ben Reyes")
    add_calibration(test_database, ana, file_id="a", accuracy="92.50")
    add_calibration(test_database, ben, status="Failed", accuracy=None)
    add_calibration(test_database, ana, file_id="old", when=utc_now() - timedelta(days=90))
    with test_database() as session:
        session.add_all([
            CommunicationHistory(user_id=ana, mode="text_to_speech", message="I need water"),
            CommunicationHistory(user_id=ana, mode="speech_to_text", message="Good morning"),
            CommunicationHistory(user_id=ben, mode="text_to_speech", message="Yes"),
        ])
        contact = SosContact(user_id=ana, contact_name="Maria Cruz", email_address="m@x.co")
        session.add(contact)
        session.flush()
        session.add_all([
            SosHistory(user_id=ana, contact_id=contact.contact_id, activation_id="a1",
                       channel="email", recipient="m@x.co", message_sent="SOS", status="sent",
                       location_text="12 Mabini St."),
            SosHistory(user_id=ana, activation_id="a1", channel="sms", recipient="0917",
                       message_sent="SOS", status="failed", error_detail="SMS not set up"),
        ])
        session.commit()
    return {"ana": ana, "ben": ben}


def test_calibration_report_default_is_last_30_days(admin, data):
    body = admin.get("/api/admin/reports/calibration").json()
    assert body["title"] == "Calibration Report"
    assert body["date_to"] == TODAY.isoformat()
    assert body["date_from"] == (TODAY - timedelta(days=29)).isoformat()
    assert body["columns"] == ["Date", "User", "Profile", "Accuracy", "Status", "Failure reason"]
    users = sorted((r[1], r[3], r[4]) for r in body["rows"])
    assert users == [("Ana Cruz", "92.50%", "Successful"), ("Ben Reyes", "", "Failed")]


def test_report_for_one_user(admin, data):
    rows = admin.get(f"/api/admin/reports/calibration?user_id={data['ben']}").json()
    assert rows["user_name"] == "Ben Reyes" and len(rows["rows"]) == 1


def test_communication_report_counts_without_text(admin, data, test_database):
    body = admin.get("/api/admin/reports/communication").json()
    assert body["columns"][:4] == ["User", "Typed", "Spoken", "Total messages"]
    assert [r[:4] for r in body["rows"]] == [["Ana Cruz", "1", "1", "2"], ["Ben Reyes", "1", "0", "1"]]
    assert "I need water" not in str(body)
    assert logs(test_database, "report_viewed") == []


def test_communication_report_with_text_is_logged(admin, data, test_database):
    body = admin.get("/api/admin/reports/communication?include_text=true").json()
    assert {r[3] for r in body["rows"]} == {"I need water", "Good morning", "Yes"}
    assert "private" in body["note"]
    assert len(logs(test_database, "report_viewed")) == 1


def test_sos_report_rows(admin, data):
    rows = admin.get("/api/admin/reports/sos").json()["rows"]
    assert [(r[2], r[3], r[5]) for r in rows] == [("Maria Cruz", "Email", "Sent"),
                                                  ("(removed contact)", "SMS", "Failed")]


def test_unknown_report_and_too_long_range(admin):
    assert admin.get("/api/admin/reports/secrets").status_code == 404
    long_ago = (TODAY - timedelta(days=400)).isoformat()
    assert admin.get(f"/api/admin/reports/sos?date_from={long_ago}").status_code == 422


# --- PDF ------------------------------------------------------------------------------------

@pytest.mark.parametrize("report_type", ["calibration", "communication", "sos"])
def test_pdf_export_is_a_real_pdf(admin, data, test_database, report_type):
    response = admin.get(f"/api/admin/reports/{report_type}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF") and response.content.rstrip().endswith(b"%%EOF")
    title = {"calibration": "Calibration", "communication": "Communication", "sos": "SOS"}[report_type]
    assert f'filename="{title}_Report_{TODAY:%Y-%m-%d}.pdf"' in response.headers["content-disposition"]
    assert f"{title}_Report_" in logs(test_database, "report_exported")[0].activity_description


def test_empty_report_still_makes_a_pdf(admin):
    response = admin.get("/api/admin/reports/sos/pdf")
    assert response.content.startswith(b"%PDF")


def test_pdf_has_page_numbers_and_handles_many_rows():
    rows = [[f"2026-11-0{i % 9 + 1} 10:00", f"User Ñiño {i}", "Desk", "90.00%", "Successful",
             "a long reason " * 8] for i in range(120)]
    report = report_service.Report("calibration", "Calibration Report",
                                   ["Date", "User", "Profile", "Accuracy", "Status",
                                    "Failure reason"], rows, TODAY, TODAY, None)
    pdf = report_pdf.render(report, "IrisClick", "PDAO Admin", datetime(2026, 11, 5, 9, 30))
    assert pdf.startswith(b"%PDF")
    pages = int(re.search(rb"/Count (\d+)", pdf).group(1))
    assert pages >= 3  # 120 wrapped rows cannot fit on one landscape page
