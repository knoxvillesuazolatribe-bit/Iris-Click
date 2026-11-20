"""The branded report design: card colours, status pills, dashes for empty cells, amber reasons."""

from datetime import date

import pytest

from app.services import report_pdf
from app.services.report_service import Report


@pytest.mark.parametrize(("label", "tone"), [
    ("Calibrations", "teal"), ("Successful", "green"), ("Failed", "red"),
    ("Average accuracy (successful)", "teal"), ("Sent", "green"), ("Not sent yet", "amber"), ("Alerts", "teal"),
])
def test_kpi_card_colours(label, tone):
    assert report_pdf.kpi_tone(label) == tone


@pytest.mark.parametrize(("status", "tone"), [
    ("Successful", "green"), ("Sent", "green"), ("Failed", "red"), ("Pending", "amber"), ("Other", "slate"),
])
def test_status_pill_colours(status, tone):
    assert report_pdf.status_tone(status) == tone


def test_empty_cells_show_a_dash_and_statuses_are_pills(monkeypatch):
    texts, pills = [], []
    real_paragraph, real_badge = report_pdf.Paragraph, report_pdf._badge
    monkeypatch.setattr(report_pdf, "Paragraph", lambda text, *a, **k: texts.append(text) or real_paragraph(text, *a, **k))
    monkeypatch.setattr(report_pdf, "_badge", lambda text, bold: pills.append(text) or real_badge(text, bold))
    report = Report("calibration", "Calibration Report", ["Date", "User", "Profile", "Accuracy", "Status", "Failure reason"],
                    [["2026-11-19 10:00", "Ana", "P1", "", "Failed", "Face not found"],
                     ["2026-11-19 11:00", "Ana", "P2", "91.0%", "Successful", ""]],
                    date(2026, 11, 1), date(2026, 11, 20), None)
    pdf = report_pdf.render(report, "IrisClick", "Admin", summary=[("Calibrations", "2")])
    assert pdf.startswith(b"%PDF")
    assert pills == ["Failed", "Successful"]
    assert texts.count(report_pdf.DASH) == 2  # the blank accuracy and the blank failure reason
    assert "IrisClick: Calibration Report" in texts and "CALIBRATIONS" in texts


def test_the_logo_ships_with_the_server():
    assert report_pdf.LOGO.exists()  # Vercel cannot read the website's files


@pytest.mark.parametrize("font", ["Helvetica-Bold", None])
@pytest.mark.parametrize("word", ["Successful", "Failed", "Sent", "Pending"])
def test_a_status_pill_never_breaks_its_word(word, font):
    """Vercel has no Arial: with Helvetica, "Failed" once broke into "Faile / d"."""
    bold = font or report_pdf._fonts()[1]
    pill = report_pdf._badge(word, bold)
    paragraph = pill._cellvalues[0][0]
    paragraph.wrap(pill._colWidths[0] - 5 * report_pdf.mm, 100)
    assert len(paragraph.blPara.lines) == 1
