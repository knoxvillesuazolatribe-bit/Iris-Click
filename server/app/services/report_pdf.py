"""PDF export of admin reports with reportlab (team decision D10)."""

from datetime import datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from app.services.report_service import Report

NAVY = colors.HexColor("#0F1B2D")
STRIPE = colors.HexColor("#EEF3FA")
MARGIN = 14 * mm
# Relative column widths per report; the page width is shared out by these.
WIDTHS = {
    "Date": 1.4, "User": 1.6, "Profile": 1.3, "Accuracy": 0.9, "Status": 0.9,
    "Failure reason": 2.6, "Type": 0.8, "Message": 5.0, "Typed": 0.8, "Spoken": 0.8,
    "Total messages": 1.1, "Last used": 1.4, "Contact": 1.4, "Channel": 0.8, "Sent to": 1.9,
    "Problem": 2.4, "Location": 2.4,
}


def _fonts() -> tuple[str, str]:
    """Arial (Windows) covers ñ and other non-English letters; Helvetica otherwise."""
    fonts = Path("C:/Windows/Fonts")
    try:
        if "IrisArial" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("IrisArial", str(fonts / "arial.ttf")))
            pdfmetrics.registerFont(TTFont("IrisArial-Bold", str(fonts / "arialbd.ttf")))
        return "IrisArial", "IrisArial-Bold"
    except Exception:  # noqa: BLE001 - not on Windows, or fonts missing
        return "Helvetica", "Helvetica-Bold"


class _NumberedCanvas(canvas.Canvas):
    """Adds "Page X of Y" once the total page count is known."""

    def __init__(self, *args, footer: str = "", font: str = "Helvetica", **kwargs):
        super().__init__(*args, **kwargs)
        self._pages = []
        self._footer, self._font = footer, font

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self.setFont(self._font, 8)
            self.setFillColor(colors.grey)
            width, _ = self._pagesize
            self.drawString(MARGIN, 8 * mm, self._footer)
            self.drawRightString(width - MARGIN, 8 * mm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def render(report: Report, app_name: str, exported_by: str, now: datetime | None = None) -> bytes:
    regular, bold = _fonts()
    now = now or datetime.now().astimezone()
    title = ParagraphStyle("title", fontName=bold, fontSize=18, leading=22, textColor=NAVY)
    meta = ParagraphStyle("meta", fontName=regular, fontSize=9.5, leading=13)
    cell = ParagraphStyle("cell", fontName=regular, fontSize=8.5, leading=10.5)
    head = ParagraphStyle("head", fontName=bold, fontSize=8.5, leading=10.5, textColor=colors.white)

    period = f"{report.date_from:%B %d, %Y} to {report.date_to:%B %d, %Y}"
    story = [
        Paragraph(escape(f"{app_name}: {report.title}"), title),
        Spacer(1, 4 * mm),
        Paragraph(escape(f"Period: {period}"), meta),
        Paragraph(escape(f"User: {report.user_name or 'Everyone'}"), meta),
        Paragraph(escape(f"Exported by {exported_by} on {now:%B %d, %Y at %I:%M %p}"), meta),
    ]
    if report.note:
        story.append(Paragraph(escape(report.note), meta))
    story.append(Spacer(1, 6 * mm))

    if not report.rows:
        story.append(Paragraph("No records in this period.", meta))
    else:
        page_width = landscape(A4)[0] - 2 * MARGIN
        weights = [WIDTHS.get(c, 1.2) for c in report.columns]
        widths = [page_width * w / sum(weights) for w in weights]
        data = [[Paragraph(escape(c), head) for c in report.columns]]
        data += [[Paragraph(escape(value).replace("\n", "<br/>"), cell) for value in row]
                 for row in report.rows]
        table = Table(data, colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D6E8")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(f"{len(report.rows)} row(s).", meta))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=16 * mm,
                            title=f"{report.title}", author=app_name)
    footer = f"{app_name} · {report.title} · {period}"
    doc.build(story, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, footer=footer, font=regular, **k))
    return buffer.getvalue()


def filename(report: Report, today: datetime | None = None) -> str:
    today = today or datetime.now().astimezone()
    return f"{report.title.replace(' ', '_')}_{today:%Y-%m-%d}.pdf"
