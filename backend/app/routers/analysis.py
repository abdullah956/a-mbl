"""OCR and text analysis (roadmap §7.2, §7.3, §10.3).

Normal results are returned and the raw text is discarded — it never touches
the database or disk. Harmful results become an encrypted case with a 30-day
expiry, and eligible High/Critical results create deduplicated in-app alerts
for the owner and any actively linked guardian.
"""

import sqlite3

from fastapi import APIRouter, Depends, File, UploadFile

from .. import classifier, config, emailer, ocr, policy, rate_limit, security, schemas
from ..db import audit, get_db, in_future, new_id, now_iso
from ..deps import active_user, case_scope
from ..errors import ApiError

router = APIRouter(tags=["analysis"])


def create_alerts_for_case(conn: sqlite3.Connection, case: sqlite3.Row,
                           recipient_ids: list[str]) -> None:
    """Insert alert rows (no raw content, deduplicated per recipient+case).

    Recipients other than the case owner also get an email when SMTP is
    configured (FR5) — only on the FIRST alert for this recipient+case, so a
    repeated share never re-sends. In-app alerts are always the fallback.
    """
    analysis = conn.execute("SELECT * FROM analysis_events WHERE id = ?",
                            (case["analysis_id"],)).fetchone()
    owner = conn.execute("SELECT display_name FROM users WHERE id = ?",
                         (case["owner_id"],)).fetchone()
    newly_alerted: list[str] = []
    for recipient_id in recipient_ids:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO alerts (id, recipient_id, case_id, severity, primary_label,"
            " subject_name, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (new_id(), recipient_id, case["id"], analysis["severity"],
             analysis["primary_label"], owner["display_name"], now_iso()),
        )
        if cursor.rowcount == 1 and recipient_id != case["owner_id"]:
            newly_alerted.append(recipient_id)

    if newly_alerted and emailer.available():
        placeholders = ",".join("?" * len(newly_alerted))
        rows = conn.execute(
            f"SELECT email, display_name FROM users WHERE id IN ({placeholders})",
            newly_alerted,
        ).fetchall()
        emailer.send_case_alerts(
            [{"email": r["email"], "displayName": r["display_name"]} for r in rows],
            severity=analysis["severity"],
            primary_label=analysis["primary_label"],
            subject_name=owner["display_name"],
        )


def _stored_prediction(analysis: sqlite3.Row) -> classifier.Prediction:
    return classifier.Prediction(
        primary_label=analysis["primary_label"],
        confidence=analysis["confidence"],
        body_shaming=bool(analysis["body_shaming"]),
        model_version=analysis["model_version"],
    )


def _result_payload(analysis: sqlite3.Row, case: sqlite3.Row | None) -> dict:
    prediction = _stored_prediction(analysis)
    uncertain = bool(analysis["needs_review"])
    return {
        "id": analysis["id"],
        "primaryLabel": analysis["primary_label"],
        "confidence": analysis["confidence"],
        "bodyShaming": bool(analysis["body_shaming"]),
        "severity": analysis["severity"],
        "needsReview": uncertain,
        "advice": policy.advice_for(prediction, uncertain),
        "modelVersion": analysis["model_version"],
        "retainedUntil": case["expires_at"] if case else None,
        "caseId": case["id"] if case else None,
    }


@router.post("/analyses", response_model=schemas.AnalysisResult, status_code=201)
def analyze(body: schemas.AnalysisRequest, user: sqlite3.Row = Depends(active_user),
            conn: sqlite3.Connection = Depends(get_db)):
    rate_limit.check(f"analyze:{user['id']}", 30)

    prediction = classifier.classify(body.text)
    severity = policy.severity_for(prediction)
    uncertain = policy.needs_review(prediction)

    analysis_id = new_id()
    conn.execute(
        "INSERT INTO analysis_events (id, owner_id, source_type, primary_label, confidence,"
        " body_shaming, severity, needs_review, model_version, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (analysis_id, user["id"], body.sourceType, prediction.primary_label,
         prediction.confidence, int(prediction.body_shaming), severity, int(uncertain),
         prediction.model_version, now_iso()),
    )

    case = None
    if policy.creates_case(severity):
        case_id = new_id()
        conn.execute(
            "INSERT INTO flagged_cases (id, analysis_id, owner_id, encrypted_text,"
            " platform_name, sender_alias, created_at, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (case_id, analysis_id, user["id"], security.encrypt_text(body.text),
             body.platformName, body.senderAlias, now_iso(),
             in_future(days=config.CASE_RETENTION_DAYS)),
        )
        case = conn.execute("SELECT * FROM flagged_cases WHERE id = ?", (case_id,)).fetchone()

        if policy.alert_eligible(prediction, severity):
            guardians = conn.execute(
                "SELECT guardian_id FROM guardian_links WHERE user_id = ? AND status = 'active'",
                (user["id"],),
            ).fetchall()
            create_alerts_for_case(conn, case, [user["id"]] + [g["guardian_id"] for g in guardians])

    audit(conn, user["id"], "analysis_created", "analysis_events", analysis_id)
    analysis = conn.execute("SELECT * FROM analysis_events WHERE id = ?", (analysis_id,)).fetchone()
    return _result_payload(analysis, case)


@router.get("/analyses/{analysis_id}", response_model=schemas.AnalysisResult)
def get_analysis(analysis_id: str, user: sqlite3.Row = Depends(active_user),
                 conn: sqlite3.Connection = Depends(get_db)):
    analysis = conn.execute("SELECT * FROM analysis_events WHERE id = ?",
                            (analysis_id,)).fetchone()
    if analysis is None:
        raise ApiError(404, "not_found", "This result is not available.")

    case = conn.execute("SELECT * FROM flagged_cases WHERE analysis_id = ?",
                        (analysis_id,)).fetchone()
    if analysis["owner_id"] != user["id"]:
        # Non-owners may only see results whose case is visible to their role.
        if case is None:
            raise ApiError(404, "not_found", "This result is not available.")
        scope_sql, params = case_scope(user)
        visible = conn.execute(
            f"SELECT 1 FROM flagged_cases fc WHERE fc.id = ? AND {scope_sql}",
            [case["id"]] + params,
        ).fetchone()
        if visible is None:
            raise ApiError(404, "not_found", "This result is not available.")
    return _result_payload(analysis, case)


@router.post("/ocr", response_model=schemas.OcrResponse)
async def run_ocr(file: UploadFile = File(...), user: sqlite3.Row = Depends(active_user),
                  conn: sqlite3.Connection = Depends(get_db)):
    rate_limit.check(f"ocr:{user['id']}", 10)
    try:
        data = await file.read(config.MAX_IMAGE_BYTES + 1)
    finally:
        await file.close()  # the temporary upload is always released
    ocr.validate_image(data)
    if not ocr.available():
        raise ApiError(503, "ocr_unavailable",
                       "Screenshot text extraction is not available on this server yet.")
    text, confidence = ocr.extract_text(data)

    audit(conn, user["id"], "ocr_completed", None, None)
    return {"text": text, "meanConfidence": confidence,
            "lowConfidence": confidence < 0.6 or not text}
