"""Role-scoped summaries and the masked PDF report (roadmap §15)."""

import sqlite3
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Response

from .. import pdf, security, schemas
from ..db import get_db, utc_now
from ..deps import active_user, case_scope
from ..errors import ApiError
from .cases import masked_preview

router = APIRouter(prefix="/reports", tags=["reports"])


def _parse_range(range_from: str | None, range_to: str | None) -> tuple[str, str, str]:
    try:
        # UTC, matching the stored created_at timestamps (local dates would
        # drop today's cases for hours in west-of-UTC timezones).
        to_day = date.fromisoformat(range_to) if range_to else utc_now().date()
        from_day = date.fromisoformat(range_from) if range_from else to_day - timedelta(days=30)
    except ValueError:
        raise ApiError(422, "validation_error", "Dates must use the YYYY-MM-DD format.")
    if from_day > to_day:
        raise ApiError(422, "validation_error", "The start date must be before the end date.")
    to_exclusive = (to_day + timedelta(days=1)).isoformat() + "T00:00:00"
    return from_day.isoformat(), to_day.isoformat(), to_exclusive


def _summary_data(conn: sqlite3.Connection, user: sqlite3.Row,
                  from_day: str, to_exclusive: str) -> dict:
    scope_sql, params = case_scope(user)
    where = (f"WHERE {scope_sql} AND fc.created_at >= ? AND fc.created_at < ?")
    range_params = params + [from_day + "T00:00:00", to_exclusive]

    rows = conn.execute(
        "SELECT ae.primary_label, ae.severity, fc.status, fc.created_at, fc.sender_alias"
        " FROM flagged_cases fc JOIN analysis_events ae ON ae.id = fc.analysis_id "
        + where, range_params,
    ).fetchall()

    by_label: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_sender: dict[str, int] = {}
    weekly: dict[str, int] = {}
    reviewed = 0
    for row in rows:
        by_label[row["primary_label"]] = by_label.get(row["primary_label"], 0) + 1
        by_severity[row["severity"]] = by_severity.get(row["severity"], 0) + 1
        if row["sender_alias"]:
            # §15.1: grouped by the alias the submitting user typed — an
            # unverified self-reported string, surfaced as such in the UI.
            by_sender[row["sender_alias"]] = by_sender.get(row["sender_alias"], 0) + 1
        if row["status"] == "reviewed":
            reviewed += 1
        day = date.fromisoformat(row["created_at"][:10])
        week_start = (day - timedelta(days=day.weekday())).isoformat()
        weekly[week_start] = weekly.get(week_start, 0) + 1

    return {
        "total": len(rows),
        "byLabel": by_label,
        "bySeverity": by_severity,
        "bySender": by_sender,
        "reviewed": reviewed,
        "pending": len(rows) - reviewed,
        "weekly": [{"weekStart": k, "count": weekly[k]} for k in sorted(weekly)],
    }


@router.get("/summary", response_model=schemas.SummaryReport)
def summary(rangeFrom: str | None = Query(default=None), rangeTo: str | None = Query(default=None),
            user: sqlite3.Row = Depends(active_user),
            conn: sqlite3.Connection = Depends(get_db)):
    from_day, to_day, to_exclusive = _parse_range(rangeFrom, rangeTo)
    data = _summary_data(conn, user, from_day, to_exclusive)
    return {"rangeFrom": from_day, "rangeTo": to_day, **data}


@router.post("/pdf")
def report_pdf(body: schemas.PdfRequest, user: sqlite3.Row = Depends(active_user),
               conn: sqlite3.Connection = Depends(get_db)):
    from_day, to_day, to_exclusive = _parse_range(body.rangeFrom, body.rangeTo)
    data = _summary_data(conn, user, from_day, to_exclusive)

    scope_sql, params = case_scope(user)
    rows = conn.execute(
        "SELECT fc.id, fc.created_at, fc.status, fc.encrypted_text,"
        " ae.primary_label, ae.confidence, ae.body_shaming, ae.severity"
        " FROM flagged_cases fc JOIN analysis_events ae ON ae.id = fc.analysis_id"
        f" WHERE {scope_sql} AND fc.created_at >= ? AND fc.created_at < ?"
        " ORDER BY fc.created_at DESC, fc.rowid DESC LIMIT 500",
        params + [from_day + "T00:00:00", to_exclusive],
    ).fetchall()

    # §15.2: review notes ride along only for cases the requester's role scope
    # already grants — the rows above ARE that scope.
    reviews_by_case: dict[str, list[dict]] = {}
    if rows:
        placeholders = ",".join("?" for _ in rows)
        review_rows = conn.execute(
            "SELECT re.case_id, re.human_label, re.encrypted_note, u.display_name"
            " FROM review_events re JOIN users u ON u.id = re.reviewer_id"
            f" WHERE re.case_id IN ({placeholders}) ORDER BY re.created_at, re.rowid",
            [r["id"] for r in rows],
        ).fetchall()
        for review in review_rows:
            reviews_by_case.setdefault(review["case_id"], []).append({
                "reviewerName": review["display_name"],
                "humanLabel": review["human_label"],
                "note": security.decrypt_text(review["encrypted_note"])
                        if review["encrypted_note"] else None,
            })

    content = pdf.build_report(
        requester_name=user["display_name"],
        requester_role=user["role"].replace("_", " "),
        range_from=from_day,
        range_to=to_day,
        summary=data,
        cases=[{
            "id": r["id"],
            "createdAt": r["created_at"],
            "primaryLabel": r["primary_label"],
            "confidence": r["confidence"],
            "bodyShaming": bool(r["body_shaming"]),
            "severity": r["severity"],
            "status": r["status"],
            "maskedPreview": masked_preview(security.decrypt_text(r["encrypted_text"])),
            "reviews": reviews_by_case.get(r["id"], []),
        } for r in rows],
    )
    return Response(content=content, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="a-mbl-report-{to_day}.pdf"',
    })
