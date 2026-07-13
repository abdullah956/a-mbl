"""Data export and account deletion (roadmap §7.5, §16).

Deletion re-checks the password, removes encrypted evidence files, and lets
SQLite foreign-key cascades remove every owned row (cases, alerts, links,
codes, memberships, sessions) in one transaction.
"""

import sqlite3

from fastapi import APIRouter, Depends

from .. import security, schemas
from ..db import audit, get_db
from ..deps import current_user
from ..errors import ApiError
from ..retention import delete_case_evidence_files

router = APIRouter(prefix="/privacy", tags=["privacy"])


@router.get("/export")
def export_data(user: sqlite3.Row = Depends(current_user),
                conn: sqlite3.Connection = Depends(get_db)):
    analyses = conn.execute(
        "SELECT id, source_type, primary_label, confidence, body_shaming, severity,"
        " needs_review, model_version, created_at FROM analysis_events WHERE owner_id = ?"
        " ORDER BY created_at", (user["id"],)).fetchall()
    cases = conn.execute(
        "SELECT * FROM flagged_cases WHERE owner_id = ? ORDER BY created_at",
        (user["id"],)).fetchall()
    links = conn.execute(
        "SELECT id, status, consented_at, revoked_at FROM guardian_links"
        " WHERE user_id = ? OR guardian_id = ?", (user["id"], user["id"])).fetchall()
    alerts = conn.execute(
        "SELECT id, case_id, severity, primary_label, created_at, read_at FROM alerts"
        " WHERE recipient_id = ?", (user["id"],)).fetchall()

    return {
        "profile": {
            "id": user["id"], "email": user["email"], "displayName": user["display_name"],
            "role": user["role"], "ageBand": user["age_band"], "status": user["status"],
            "createdAt": user["created_at"],
        },
        "analyses": [dict(a) for a in analyses],
        "cases": [{
            "id": c["id"], "status": c["status"], "platformName": c["platform_name"],
            "senderAlias": c["sender_alias"], "createdAt": c["created_at"],
            "expiresAt": c["expires_at"],
            "text": security.decrypt_text(c["encrypted_text"]),
        } for c in cases],
        "guardianLinks": [dict(l) for l in links],
        "alerts": [dict(a) for a in alerts],
    }


@router.delete("/account", status_code=204)
def delete_account(body: schemas.DeleteAccountRequest,
                   user: sqlite3.Row = Depends(current_user),
                   conn: sqlite3.Connection = Depends(get_db)):
    if not security.verify_password(body.password, user["password_hash"]):
        raise ApiError(401, "invalid_credentials", "The password is incorrect.")

    owned_cases = conn.execute(
        "SELECT id FROM flagged_cases WHERE owner_id = ?", (user["id"],)).fetchall()
    failed = [case for case in owned_cases
              if not delete_case_evidence_files(conn, case["id"])]
    if failed:
        # Abort before dropping rows: keep the records that let cleanup retry.
        raise ApiError(503, "cleanup_retry",
                       "Stored evidence could not be removed. Try again shortly.")

    # §7.5: only de-identified aggregate counters may remain — audit rows keep
    # their action/timestamp for counting but lose every reference to the
    # account, whether it acted (actor_id) or was acted upon (object_id).
    conn.execute("UPDATE audit_events SET actor_id = NULL WHERE actor_id = ?", (user["id"],))
    conn.execute("UPDATE audit_events SET object_id = NULL WHERE object_id = ?", (user["id"],))
    conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    audit(conn, None, "account_deleted", "users", None)  # de-identified
