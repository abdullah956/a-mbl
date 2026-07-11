"""Retention cleanup (roadmap §16.2).

Runs at startup and every 24 hours: expired harmful cases are deleted together
with their encrypted evidence files; stale one-time codes and dead refresh
tokens are purged. File deletion failures are recorded without the path and
retried on the next run (the DB row is only removed after the file is gone).
"""

import sqlite3

from . import config
from .db import audit, now_iso


def evidence_file(evidence_id: str):
    return config.data_dir() / "evidence" / f"{evidence_id}.bin"


def delete_case_evidence_files(conn: sqlite3.Connection, case_id: str) -> bool:
    """Unlink evidence files for a case. Returns False if any unlink failed."""
    ok = True
    rows = conn.execute("SELECT id FROM case_evidence WHERE case_id = ?", (case_id,)).fetchall()
    for row in rows:
        path = evidence_file(row["id"])
        try:
            path.unlink(missing_ok=True)
        except OSError:
            audit(conn, None, "evidence_cleanup_failed", "case_evidence", row["id"])
            ok = False
    return ok


def cleanup(conn: sqlite3.Connection) -> dict:
    now = now_iso()
    expired = conn.execute(
        "SELECT id FROM flagged_cases WHERE expires_at <= ?", (now,)
    ).fetchall()

    removed = 0
    for case in expired:
        if delete_case_evidence_files(conn, case["id"]):
            conn.execute("DELETE FROM flagged_cases WHERE id = ?", (case["id"],))
            removed += 1

    codes = conn.execute(
        "DELETE FROM guardian_link_codes WHERE expires_at <= ? OR consumed_at IS NOT NULL",
        (now,),
    ).rowcount
    tokens = conn.execute(
        "DELETE FROM refresh_tokens WHERE expires_at <= ?", (now,)
    ).rowcount

    if removed:
        audit(conn, None, "retention_cleanup", "flagged_cases", f"count:{removed}")
    conn.commit()
    return {"casesRemoved": removed, "codesRemoved": codes, "tokensRemoved": tokens}
