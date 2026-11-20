"""PDF export of admin reports with reportlab (team decision D10), in IrisClick's teal-and-slate design:
a branded header (logo, title, teal accent bar, Period / User / Exported pills), coloured KPI cards,
a teal table with status pills and dashes for empty cells, and a styled footer on every page."""

from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.local_time import now_local
from app.services.report_service import Report

# Brand colours (the website's teal and slate).
TEAL = colors.HexColor("#0F766E")
TEAL_DARK = colors.HexColor("#115E59")
TEAL_TINT = colors.HexColor("#F0FDFA")
TEAL_LINE = colors.HexColor("#99F6E4")
SLATE = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
BORDER = colors.HexColor("#E2E8F0")
STRIPE = colors.HexColor("#F8FAFC")
AMBER_TEXT = colors.HexColor("#B45309")
# Tones for KPI cards and status pills: (background, border, text).
TONES = {
    "teal": (TEAL_TINT, TEAL_LINE, TEAL),
    "green": (colors.HexColor("#ECFDF5"), colors.HexColor("#A7F3D0"), colors.HexColor("#047857")),
    "red": (colors.HexColor("#FEF2F2"), colors.HexColor("#FECACA"), colors.HexColor("#B91C1C")),
    "amber": (colors.HexColor("#FFFBEB"), colors.HexColor("#FDE68A"), AMBER_TEXT),
    "slate": (STRIPE, BORDER, colors.HexColor("#334155")),
}
LOGO = Path(__file__).resolve().parents[1] / "assets" / "irisclick-logo.png"
MARGIN = 14 * mm
DASH = "\u2014"
# Relative column widths per report; the page width is shared out by these.
WIDTHS = {
    "Date": 1.4, "User": 1.6, "Profile": 1.3, "Accuracy": 0.9, "Status": 1.15,
    "Failure reason": 2.6, "Type": 0.8, "Message": 5.0, "Typed": 0.8, "Spoken": 0.8,
    "Total messages": 1.1, "Last used": 1.4, "Contact": 1.4, "Channel": 1.05, "Sent to": 1.9,
    "Problem": 2.4, "Location": 2.4, "Alert message": 2.6,
}
STATUS_COLUMN = "Status"
REASON_COLUMNS = {"Failure reason", "Problem"}  # shown in a muted amber, for quick scanning
NO_RECORDS = "No records found for these filters."


def kpi_tone(label: str) -> str:
    """Colour of a summary card: red for failures, green for successes, amber for waiting, else teal."""
    text = label.lower()
    if "average" in text or "accuracy" in text:
        return "teal"
    if "fail" in text:
        return "red"
    if "success" in text or text == "sent":
        return "green"
    if "not sent" in text or "pending" in text:
        return "amber"
    return "teal"


def status_tone(value: str) -> str:
    return {"successful": "green", "sent": "green", "failed": "red", "pending": "amber"}.get(
        value.strip().lower(), "slate")


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
    """Footer on every page: a teal rule, the report line and "Page X of Y"."""

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
            width, _ = self._pagesize
            self.setStrokeColor(TEAL_LINE)
            self.setLineWidth(0.8)
            self.line(MARGIN, 11 * mm, width - MARGIN, 11 * mm)
            self.setFont(self._font, 8)
            self.setFillColor(MUTED)
            self.drawString(MARGIN, 7 * mm, self._footer)
            self.setFillColor(TEAL)
            self.drawRightString(width - MARGIN, 7 * mm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def _card(content: list, tone: str, padding: float = 3.2 * mm, heights: list | None = None) -> Table:
    background, border, _ = TONES[tone]
    card = Table([[item] for item in content], rowHeights=heights)
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("BOX", (0, 0), (-1, -1), 0.6, border),
        ("ROUNDEDCORNERS", [2.5 * mm] * 4),
        ("LEFTPADDING", (0, 0), (-1, -1), padding), ("RIGHTPADDING", (0, 0), (-1, -1), padding),
        ("TOPPADDING", (0, 0), (0, 0), padding), ("BOTTOMPADDING", (0, -1), (-1, -1), padding),
        ("TOPPADDING", (0, 1), (-1, -1), 0.8 * mm), ("BOTTOMPADDING", (0, 0), (-1, -2), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return card


def _row_of(cells: list, width: float, gap: float = 4 * mm) -> Table:
    """Cards side by side with even gaps, filling ``width``."""
    count = len(cells)
    each = (width - gap * (count - 1)) / count
    data, widths = [], []
    for i, cell in enumerate(cells):
        data.append(cell)
        widths.append(each)
        if i < count - 1:
            data.append("")
            widths.append(gap)
    row = Table([data], colWidths=widths, hAlign="LEFT")
    row.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                             ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return row


def _header(report: Report, app_name: str, exported_by: str, now: datetime, width: float,
            regular: str, bold: str) -> list:
    kicker = ParagraphStyle("kicker", fontName=bold, fontSize=8, leading=10, textColor=TEAL)
    title = ParagraphStyle("title", fontName=bold, fontSize=21, leading=25, textColor=SLATE)
    pill_label = ParagraphStyle("pill-label", fontName=bold, fontSize=7, leading=9, textColor=TEAL)
    pill_value = ParagraphStyle("pill-value", fontName=bold, fontSize=10, leading=12.5, textColor=SLATE)
    note = ParagraphStyle("note", fontName=regular, fontSize=8.5, leading=11, textColor=MUTED)

    words = [Paragraph("PDAO REPORT", kicker), Paragraph(escape(f"{app_name}: {report.title}"), title)]
    if LOGO.exists():
        logo_h = 15 * mm
        logo = Image(str(LOGO), width=logo_h * 324 / 172, height=logo_h)
        top = Table([[logo, words]], colWidths=[logo_h * 324 / 172 + 5 * mm, None], hAlign="LEFT")
    else:
        top = Table([[words]], hAlign="LEFT")
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))

    accent = Table([[""]], colWidths=[width], rowHeights=[1.4 * mm])
    accent.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL),
                                ("ROUNDEDCORNERS", [0.7 * mm] * 4)]))

    period = f"{report.date_from:%B %d, %Y} to {report.date_to:%B %d, %Y}"
    pills = [("PERIOD", period), ("USER", report.user_name or "Everyone"),
             ("EXPORTED", f"{now:%B %d, %Y, %I:%M %p} by {exported_by}")]
    pill_row = _row_of([_card([Paragraph(label, pill_label), Paragraph(escape(value), pill_value)], "teal",
                              padding=2.6 * mm) for label, value in pills], width)
    story = [top, Spacer(1, 3.5 * mm), accent, Spacer(1, 4 * mm), pill_row]
    if report.note:
        story += [Spacer(1, 2.5 * mm), Paragraph(escape(report.note), note)]
    return story


def _kpis(summary: list[tuple[str, str]], width: float, regular: str, bold: str) -> Table:
    # Same height for every card: as many label lines as the longest label needs.
    gap, padding = 4 * mm, 3.2 * mm
    inner = (width - gap * (len(summary) - 1)) / len(summary) - 2 * padding
    lines = max(1 + int(pdfmetrics.stringWidth(label.upper(), bold, 7.5) > inner) for label, _ in summary)
    heights = [padding + 9.5 * lines, 26 + 0.8 * mm + padding]
    cards = []
    for label, value in summary:
        _, _, ink = TONES[kpi_tone(label)]
        label_style = ParagraphStyle("kpi-label", fontName=bold, fontSize=7.5, leading=9.5, textColor=MUTED)
        value_style = ParagraphStyle("kpi-value", fontName=bold, fontSize=22, leading=26, textColor=ink)
        cards.append(_card([Paragraph(escape(label.upper()), label_style), Paragraph(escape(value), value_style)],
                           kpi_tone(label), padding, heights))
    return _row_of(cards, width)


def _badge(text: str, bold: str) -> Table:
    """A pill as wide as its word: soft background, thin border, dark text of the same colour."""
    background, border, ink = TONES[status_tone(text)]
    style = ParagraphStyle("badge", fontName=bold, fontSize=7.5, leading=9, textColor=ink)
    pill = Table([[Paragraph(escape(text), style)]], colWidths=[pdfmetrics.stringWidth(text, bold, 7.5) + 5 * mm],
                 hAlign="LEFT")
    pill.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background), ("BOX", (0, 0), (-1, -1), 0.5, border),
        ("ROUNDEDCORNERS", [2.2 * mm] * 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 0.9 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.1 * mm),
    ]))
    return pill


def render(report: Report, app_name: str, exported_by: str, now: datetime | None = None,
           summary: list[tuple[str, str]] | None = None) -> bytes:
    regular, bold = _fonts()
    now = now or now_local()  # Philippine time, also on Vercel's UTC servers
    width = landscape(A4)[0] - 2 * MARGIN
    cell = ParagraphStyle("cell", fontName=regular, fontSize=8.5, leading=11, textColor=SLATE)
    empty = ParagraphStyle("empty", parent=cell, textColor=colors.HexColor("#94A3B8"))
    reason = ParagraphStyle("reason", parent=cell, textColor=AMBER_TEXT)
    head = ParagraphStyle("head", fontName=bold, fontSize=8.5, leading=11, textColor=colors.white)
    count_style = ParagraphStyle("count", fontName=regular, fontSize=8.5, leading=11, textColor=MUTED)

    story = _header(report, app_name, exported_by, now, width, regular, bold)
    if summary:
        story += [Spacer(1, 5 * mm), _kpis(summary, width, regular, bold)]
    story.append(Spacer(1, 6 * mm))

    # An empty result still exports: the table header, then a note.
    weights = [WIDTHS.get(c, 1.2) for c in report.columns]
    widths = [width * w / sum(weights) for w in weights]

    def styled(column: str, value: str):
        if not value.strip():
            return Paragraph(DASH, empty)
        if column == STATUS_COLUMN:
            return _badge(value, bold)
        return Paragraph(escape(value).replace("\n", "<br/>"), reason if column in REASON_COLUMNS else cell)

    data = [[Paragraph(escape(c), head) for c in report.columns]]
    data += [[styled(c, value) for c, value in zip(report.columns, row)] for row in report.rows]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, TEAL_DARK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, BORDER),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2.4 * mm),
        ("TOPPADDING", (0, 0), (-1, 0), 2.6 * mm), ("BOTTOMPADDING", (0, 0), (-1, 0), 2.6 * mm),
        ("TOPPADDING", (0, 1), (-1, -1), 2.0 * mm), ("BOTTOMPADDING", (0, 1), (-1, -1), 2.0 * mm),
    ]))
    story.append(table)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"{len(report.rows)} row(s)." if report.rows else NO_RECORDS, count_style))

    period = f"{report.date_from:%B %d, %Y} to {report.date_to:%B %d, %Y}"
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=17 * mm,
                            title=f"{report.title}", author=app_name)
    footer = f"{app_name} \u00b7 {report.title} \u00b7 {period}"
    doc.build(story, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, footer=footer, font=regular, **k))
    return buffer.getvalue()


def filename(report: Report, today: datetime | None = None) -> str:
    today = today or now_local()
    return f"{report.title.replace(' ', '_')}_{today:%Y-%m-%d}.pdf"
