"""Role-scoped in-app alert inbox (roadmap §14). Previews never contain raw
content — only severity, category, subject name, and time."""

import sqlite3

from fastapi import APIRouter, Depends

from .. import schemas
from ..db import get_db, now_iso
from ..deps import active_user
from ..errors import ApiError

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _out(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "caseId": row["case_id"],
        "severity": row["severity"],
        "primaryLabel": row["primary_label"],
        "subjectName": row["subject_name"],
        "createdAt": row["created_at"],
        "readAt": row["read_at"],
    }


@router.get("", response_model=list[schemas.AlertOut])
def list_alerts(user: sqlite3.Row = Depends(active_user),
                conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT * FROM alerts WHERE recipient_id = ? ORDER BY created_at DESC LIMIT 200",
        (user["id"],),
    ).fetchall()
    return [_out(r) for r in rows]


@router.patch("/{alert_id}", response_model=schemas.AlertOut)
def mark_read(alert_id: str, body: schemas.PatchAlertRequest,
              user: sqlite3.Row = Depends(active_user),
              conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute("SELECT * FROM alerts WHERE id = ? AND recipient_id = ?",
                       (alert_id, user["id"])).fetchone()
    if row is None:
        raise ApiError(404, "not_found", "This alert is not available.")
    if body.read and row["read_at"] is None:
        conn.execute("UPDATE alerts SET read_at = ? WHERE id = ?", (now_iso(), alert_id))
        row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
    return _out(row)
