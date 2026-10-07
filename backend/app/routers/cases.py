"""Case history, human review, evidence, and organization sharing.

Every query goes through the role scope in deps.case_scope. The original
model result is immutable — human reviews are separate rows. Evidence is one
explicitly attached screenshot, stored encrypted and deleted with the case.
"""

import hashlib
import sqlite3

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile

from .. import classifier, config, ocr, policy, rate_limit, security, schemas
from ..db import audit, get_db, new_id, now_iso
from ..deps import active_user, case_scope, load_case, require_case_owner
from ..errors import ApiError
from ..retention import delete_case_evidence_files, evidence_file
from .analysis import create_alerts_for_case, stored_prediction

router = APIRouter(prefix="/cases", tags=["cases"])

_SUMMARY_SQL = """
SELECT fc.*, ae.primary_label, ae.confidence, ae.body_shaming, ae.severity,
       ae.needs_review, ae.source_type, ae.model_version,
       u.display_name AS owner_name,
       (SELECT COUNT(*) FROM case_evidence ce WHERE ce.case_id = fc.id) AS evidence_count,
       (SELECT COUNT(*) FROM review_events re WHERE re.case_id = fc.id) AS review_count
FROM flagged_cases fc
JOIN analysis_events ae ON ae.id = fc.analysis_id
JOIN users u ON u.id = fc.owner_id
"""


def masked_preview(text: str) -> str:
    """Masked previews are computed on demand — the database keeps only the
    encrypted text, never a partially masked plaintext copy."""
    prediction = classifier.classify(text)
    if prediction.primary_label != "normal" and not prediction.matched_terms:
        # Model-flagged with no literal term to censor: withhold the preview
        # rather than leak raw content (detail view still decrypts in full).
        return "Content withheld — open the case to view it."
    return classifier.mask_text(text, prediction.matched_terms)


def _summary(row: sqlite3.Row, viewer_id: str) -> dict:
    return {
        "id": row["id"],
        "primaryLabel": row["primary_label"],
        "severity": row["severity"],
        "confidence": row["confidence"],
        "bodyShaming": bool(row["body_shaming"]),
        "status": row["status"],
        "sourceType": row["source_type"],
        "ownerName": row["owner_name"],
        "isOwn": row["owner_id"] == viewer_id,
        "platformName": row["platform_name"],
        "senderAlias": row["sender_alias"],
        "createdAt": row["created_at"],
        "expiresAt": row["expires_at"],
        "hasEvidence": row["evidence_count"] > 0,
        "reviewCount": row["review_count"],
        "reviewRequested": bool(row["review_requested"]),
    }


def _detail(conn: sqlite3.Connection, user: sqlite3.Row, case_id: str) -> dict:
    scope_sql, params = case_scope(user)
    row = conn.execute(
        f"{_SUMMARY_SQL} WHERE fc.id = ? AND {scope_sql}", [case_id] + params
    ).fetchone()
    if row is None:
        raise ApiError(404, "not_found", "This case is not available.")

    reviews = conn.execute(
        "SELECT re.*, u.display_name, u.role FROM review_events re"
        " JOIN users u ON u.id = re.reviewer_id WHERE re.case_id = ? ORDER BY re.created_at, re.rowid",
        (case_id,),
    ).fetchall()
    shares = []
    if row["owner_id"] == user["id"]:
        shares = conn.execute(
            "SELECT cs.*, o.name FROM case_shares cs JOIN organizations o ON o.id = cs.organization_id"
            " WHERE cs.case_id = ? AND cs.revoked_at IS NULL ORDER BY cs.shared_at",
            (case_id,),
        ).fetchall()
    evidence = conn.execute(
        "SELECT * FROM case_evidence WHERE case_id = ? ORDER BY created_at", (case_id,)
    ).fetchall()

    text = security.decrypt_text(row["encrypted_text"])
    return {
        **_summary(row, user["id"]),
        "text": text,
        "maskedPreview": masked_preview(text),
        "needsReview": bool(row["needs_review"]),
        "modelVersion": row["model_version"],
        "reviews": [{
            "id": r["id"],
            "reviewerName": r["display_name"],
            "reviewerRole": r["role"],
            "humanLabel": r["human_label"],
            "note": security.decrypt_text(r["encrypted_note"]) if r["encrypted_note"] else None,
            "createdAt": r["created_at"],
        } for r in reviews],
        "shares": [{
            "id": s["id"],
            "organizationId": s["organization_id"],
            "organizationName": s["name"],
            "sharedAt": s["shared_at"],
        } for s in shares],
        "evidence": [{
            "id": e["id"],
            "mimeType": e["mime_type"],
            "sizeBytes": e["size_bytes"],
            "createdAt": e["created_at"],
        } for e in evidence],
    }


@router.get("", response_model=schemas.CaseListResponse)
def list_cases(
    severity: str | None = Query(default=None),
    label: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    user: sqlite3.Row = Depends(active_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    scope_sql, params = case_scope(user)
    filters, filter_params = "", []
    if severity:
        filters += " AND ae.severity = ?"
        filter_params.append(severity)
    if label:
        filters += " AND ae.primary_label = ?"
        filter_params.append(label)
    if status:
        filters += " AND fc.status = ?"
        filter_params.append(status)

    where = f"WHERE {scope_sql}{filters}"
    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM flagged_cases fc"
        f" JOIN analysis_events ae ON ae.id = fc.analysis_id {where}",
        params + filter_params,
    ).fetchone()["n"]
    # Timestamps have one-second resolution; rowid keeps cases created in the
    # same second newest-first instead of in arbitrary order.
    rows = conn.execute(
        f"{_SUMMARY_SQL} {where} ORDER BY fc.created_at DESC, fc.rowid DESC LIMIT ? OFFSET ?",
        params + filter_params + [pageSize, (page - 1) * pageSize],
    ).fetchall()
    return {"items": [_summary(r, user["id"]) for r in rows], "total": total,
            "page": page, "pageSize": pageSize}


@router.get("/{case_id}", response_model=schemas.CaseDetail)
def get_case(case_id: str, user: sqlite3.Row = Depends(active_user),
             conn: sqlite3.Connection = Depends(get_db)):
    return _detail(conn, user, case_id)


@router.patch("/{case_id}", response_model=schemas.CaseDetail)
def patch_case(case_id: str, body: schemas.PatchCaseRequest,
               user: sqlite3.Row = Depends(active_user),
               conn: sqlite3.Connection = Depends(get_db)):
    case = load_case(conn, user, case_id)
    require_case_owner(user, case)
    if body.platformName is not None:
        conn.execute("UPDATE flagged_cases SET platform_name = ? WHERE id = ?",
                     (body.platformName.strip() or None, case_id))
    if body.senderAlias is not None:
        conn.execute("UPDATE flagged_cases SET sender_alias = ? WHERE id = ?",
                     (body.senderAlias.strip() or None, case_id))
    if body.requestReview:
        conn.execute("UPDATE flagged_cases SET review_requested = 1 WHERE id = ?", (case_id,))
        audit(conn, user["id"], "review_requested", "flagged_cases", case_id)
    return _detail(conn, user, case_id)


@router.delete("/{case_id}", status_code=204)
def delete_case(case_id: str, user: sqlite3.Row = Depends(active_user),
                conn: sqlite3.Connection = Depends(get_db)):
    case = load_case(conn, user, case_id)
    require_case_owner(user, case)
    if not delete_case_evidence_files(conn, case_id):
        # Keep the row so the failed unlink can be retried (here or by cleanup).
        # Commit first: the error would otherwise roll back the audit record
        # of the failure along with everything else.
        conn.commit()
        raise ApiError(503, "cleanup_retry",
                       "The attached screenshot could not be removed. Try again shortly.")
    conn.execute("DELETE FROM flagged_cases WHERE id = ?", (case_id,))
    audit(conn, user["id"], "case_deleted", "flagged_cases", case_id)


@router.post("/{case_id}/reviews", response_model=schemas.ReviewOut, status_code=201)
def add_review(case_id: str, body: schemas.ReviewRequest,
               user: sqlite3.Row = Depends(active_user),
               conn: sqlite3.Connection = Depends(get_db)):
    load_case(conn, user, case_id)  # any authorized viewer may review
    if body.humanLabel is None and not (body.note or "").strip():
        raise ApiError(422, "validation_error", "Add a category or a note.",
                       {"note": "Add a category or a note."})

    review_id = new_id()
    note = (body.note or "").strip()
    created = now_iso()
    conn.execute(
        "INSERT INTO review_events (id, case_id, reviewer_id, human_label, encrypted_note, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (review_id, case_id, user["id"], body.humanLabel,
         security.encrypt_text(note) if note else None, created),
    )
    conn.execute("UPDATE flagged_cases SET status = 'reviewed', review_requested = 0"
                 " WHERE id = ?", (case_id,))
    audit(conn, user["id"], "review_added", "review_events", review_id)
    return {"id": review_id, "reviewerName": user["display_name"], "reviewerRole": user["role"],
            "humanLabel": body.humanLabel, "note": note or None, "createdAt": created}


@router.post("/{case_id}/evidence", response_model=schemas.EvidenceOut, status_code=201)
async def attach_evidence(case_id: str, file: UploadFile = File(...),
                          user: sqlite3.Row = Depends(active_user),
                          conn: sqlite3.Connection = Depends(get_db)):
    rate_limit.check(f"evidence:{user['id']}", 10)
    case = load_case(conn, user, case_id)
    require_case_owner(user, case)
    if conn.execute("SELECT 1 FROM case_evidence WHERE case_id = ?", (case_id,)).fetchone():
        raise ApiError(409, "evidence_exists", "This case already has an attached screenshot.")

    try:
        # Never buffer more than the limit + 1 byte, whatever the client sends.
        data = await file.read(config.MAX_IMAGE_BYTES + 1)
    finally:
        await file.close()
    mime = ocr.validate_image(data)

    evidence_id = new_id()
    created = now_iso()
    evidence_file(evidence_id).write_bytes(security.encrypt_bytes(data))
    conn.execute(
        "INSERT INTO case_evidence (id, case_id, file_name, mime_type, size_bytes, content_hash, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (evidence_id, case_id, "screenshot", mime, len(data),
         hashlib.sha256(data).hexdigest(), created),
    )
    audit(conn, user["id"], "evidence_attached", "case_evidence", evidence_id)
    return {"id": evidence_id, "mimeType": mime, "sizeBytes": len(data), "createdAt": created}


@router.get("/{case_id}/evidence/{evidence_id}")
def get_evidence(case_id: str, evidence_id: str, user: sqlite3.Row = Depends(active_user),
                 conn: sqlite3.Connection = Depends(get_db)):
    load_case(conn, user, case_id)
    row = conn.execute("SELECT * FROM case_evidence WHERE id = ? AND case_id = ?",
                       (evidence_id, case_id)).fetchone()
    if row is None:
        raise ApiError(404, "not_found", "This evidence is not available.")
    encrypted = evidence_file(evidence_id)
    if not encrypted.exists():
        raise ApiError(404, "not_found", "This evidence is not available.")
    data = security.decrypt_bytes(encrypted.read_bytes())
    if data is None:
        raise ApiError(404, "not_found", "This evidence is not available.")
    return Response(content=data, media_type=row["mime_type"])


@router.post("/{case_id}/shares", response_model=schemas.ShareOut, status_code=201)
def share_case(case_id: str, body: schemas.ShareRequest,
               user: sqlite3.Row = Depends(active_user),
               conn: sqlite3.Connection = Depends(get_db)):
    case = load_case(conn, user, case_id)
    require_case_owner(user, case)

    org = conn.execute("SELECT * FROM organizations WHERE id = ? AND status = 'active'",
                       (body.organizationId,)).fetchone()
    if org is None:
        raise ApiError(404, "not_found", "This organization is not available.")
    if conn.execute(
        "SELECT 1 FROM case_shares WHERE case_id = ? AND organization_id = ? AND revoked_at IS NULL",
        (case_id, org["id"]),
    ).fetchone():
        raise ApiError(409, "already_shared", "This case is already shared with that organization.")

    share_id = new_id()
    shared = now_iso()
    conn.execute(
        "INSERT INTO case_shares (id, case_id, organization_id, shared_by, shared_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (share_id, case_id, org["id"], user["id"], shared),
    )
    audit(conn, user["id"], "case_shared", "case_shares", share_id)

    # Alert the organization's administrators when the case is alert-eligible.
    analysis = conn.execute("SELECT * FROM analysis_events WHERE id = ?",
                            (case["analysis_id"],)).fetchone()
    if policy.alert_eligible(stored_prediction(analysis), analysis["severity"]):
        admins = conn.execute(
            "SELECT user_id FROM organization_memberships"
            " WHERE organization_id = ? AND status = 'active'",
            (org["id"],),
        ).fetchall()
        create_alerts_for_case(conn, case, [a["user_id"] for a in admins])

    return {"id": share_id, "organizationId": org["id"], "organizationName": org["name"],
            "sharedAt": shared}


@router.delete("/{case_id}/shares/{share_id}", status_code=204)
def revoke_share(case_id: str, share_id: str, user: sqlite3.Row = Depends(active_user),
                 conn: sqlite3.Connection = Depends(get_db)):
    case = load_case(conn, user, case_id)
    require_case_owner(user, case)
    share = conn.execute(
        "SELECT * FROM case_shares WHERE id = ? AND case_id = ? AND revoked_at IS NULL",
        (share_id, case_id),
    ).fetchone()
    if share is None:
        raise ApiError(404, "not_found", "This share is not available.")
    conn.execute("UPDATE case_shares SET revoked_at = ? WHERE id = ?", (now_iso(), share_id))
    # Remove this organization's alerts for the case — but only for recipients
    # whose ONLY visibility came from this share (never the owner, an actively
    # linked guardian, or a member of another organization with a live share).
    conn.execute(
        """
        DELETE FROM alerts WHERE case_id = :case_id
          AND recipient_id IN (
            SELECT user_id FROM organization_memberships WHERE organization_id = :org_id)
          AND recipient_id != :owner_id
          AND recipient_id NOT IN (
            SELECT guardian_id FROM guardian_links
            WHERE user_id = :owner_id AND status = 'active')
          AND recipient_id NOT IN (
            SELECT m.user_id FROM organization_memberships m
            JOIN case_shares cs ON cs.organization_id = m.organization_id
            WHERE cs.case_id = :case_id AND cs.revoked_at IS NULL
              AND m.status = 'active')
        """,
        {"case_id": case_id, "org_id": share["organization_id"], "owner_id": case["owner_id"]},
    )
    audit(conn, user["id"], "case_share_revoked", "case_shares", share_id)
