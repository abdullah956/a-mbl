"""Masked, role-scoped PDF report (roadmap §15.2).

Built fully in memory — no temporary files to clean up. The default report
never contains raw messages, emails, tokens, screenshots, paths, or key
material; previews come pre-masked from the case table.
"""

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .db import now_iso

DISCLAIMER = (
    "Classifications in this report are automated estimates produced for human "
    "review. They are not judgments about a person or incident. Content previews "
    "are masked by default."
)


def build_report(*, requester_name: str, requester_role: str, range_from: str,
                 range_to: str, summary: dict, cases: list[dict]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title="a-mbl case report",
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8, leading=10)

    story = [
        Paragraph("a-mbl — masked case report", styles["Title"]),
        # Paragraph() parses its text as mini-XML, so anything user-derived
        # (display names, masked case text) must be escaped or it raises.
        Paragraph(f"Scope: {requester_role} — {escape(requester_name)}", styles["BodyText"]),
        Paragraph(f"Date range: {range_from[:10]} to {range_to[:10]}", styles["BodyText"]),
        Paragraph(f"Generated: {now_iso()}", styles["BodyText"]),
        Spacer(1, 6 * mm),
        Paragraph(
            f"Total cases: {summary['total']} — reviewed {summary['reviewed']}, "
            f"pending {summary['pending']}", styles["Heading3"]),
        Paragraph(
            "By category: " + (", ".join(f"{k}: {v}" for k, v in summary["byLabel"].items()) or "none"),
            styles["BodyText"]),
        Paragraph(
            "By severity: " + (", ".join(f"{k}: {v}" for k, v in summary["bySeverity"].items()) or "none"),
            styles["BodyText"]),
        Paragraph(
            "By sender alias (as entered by users, unverified): "
            + (", ".join(f"{escape(k)}: {v}" for k, v in summary.get("bySender", {}).items()) or "none"),
            styles["BodyText"]),
        Spacer(1, 6 * mm),
    ]

    # Each cell must fit inside one A4 frame, so review notes are capped in
    # both count and length — an unbounded note would raise LayoutError and
    # 500 the whole report.
    NOTE_LIMIT = 240

    def _preview_cell(case: dict) -> list:
        cell = [Paragraph(escape(case["maskedPreview"]), small)]
        reviews = case.get("reviews", [])
        for review in reviews[:5]:
            line = f"Review by {escape(review['reviewerName'])}"
            if review.get("humanLabel"):
                line += f" — {escape(review['humanLabel'])}"
            note = review.get("note")
            if note:
                trimmed = note[:NOTE_LIMIT] + "…" if len(note) > NOTE_LIMIT else note
                line += f": {escape(trimmed)}"
            cell.append(Paragraph(line, small))
        if len(reviews) > 5:
            cell.append(Paragraph(f"(+{len(reviews) - 5} more reviews)", small))
        return cell

    header = ["Case", "Date", "Category", "Conf.", "Body shaming", "Severity", "Status", "Masked preview and reviews"]
    rows = [header] + [[
        case["id"][:8],
        case["createdAt"][:10],
        case["primaryLabel"],
        f"{round(case['confidence'] * 100)}%",
        "yes" if case["bodyShaming"] else "no",
        case["severity"],
        case["status"],
        _preview_cell(case),
    ] for case in cases]

    table = Table(rows, colWidths=[18 * mm, 20 * mm, 22 * mm, 13 * mm, 18 * mm, 18 * mm, 18 * mm, None])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e4f3")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9c4d4")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f5fb")]),
    ]))
    story += [table, Spacer(1, 8 * mm), Paragraph(DISCLAIMER, small)]

    doc.build(story)
    return buffer.getvalue()
