"""Guardian links and organizations (roadmap §5, §10.2).

A pending 13–17 user shares a one-time code with their guardian; approval
activates the account. Either side can revoke without deleting accounts.
A guardian link never grants access beyond the linked user's cases.
"""

import sqlite3

from fastapi import APIRouter, Depends

from .. import config, rate_limit, security, schemas
from ..db import audit, get_db, in_future, new_id, now_iso
from ..deps import active_user, current_user
from ..errors import ApiError

router = APIRouter(tags=["links"])


def _link_out(conn: sqlite3.Connection, link: sqlite3.Row) -> dict:
    user = conn.execute("SELECT display_name, age_band FROM users WHERE id = ?",
                        (link["user_id"],)).fetchone()
    guardian = conn.execute("SELECT display_name FROM users WHERE id = ?",
                            (link["guardian_id"],)).fetchone()
    return {
        "id": link["id"],
        "status": link["status"],
        "userName": user["display_name"] if user else "Removed account",
        "userAgeBand": user["age_band"] if user else "-",
        "guardianName": guardian["display_name"] if guardian else "Removed account",
        "consentedAt": link["consented_at"],
    }


@router.post("/guardian-links", response_model=schemas.CreateLinkCodeResponse, status_code=201)
def create_code(user: sqlite3.Row = Depends(current_user),
                conn: sqlite3.Connection = Depends(get_db)):
    if user["role"] != "user":
        raise ApiError(403, "forbidden", "Only user accounts create guardian link codes.")
    rate_limit.check(f"link-code:{user['id']}", 5)

    code = security.new_link_code()
    expires = in_future(hours=config.GUARDIAN_CODE_HOURS)
    conn.execute(
        "INSERT INTO guardian_link_codes (id, code_hash, user_id, expires_at) VALUES (?, ?, ?, ?)",
        (new_id(), security.sha256_hex(code), user["id"], expires),
    )
    audit(conn, user["id"], "link_code_created", "guardian_link_codes", None)
    return {"code": code, "expiresAt": expires}


def _valid_code_row(conn: sqlite3.Connection, code: str) -> sqlite3.Row:
    code_row = conn.execute(
        "SELECT * FROM guardian_link_codes WHERE code_hash = ? AND consumed_at IS NULL"
        " AND expires_at > ?",
        (security.sha256_hex(code.strip().upper()), now_iso()),
    ).fetchone()
    if code_row is None:
        raise ApiError(404, "code_invalid", "This code is not valid or has expired.")
    return code_row


@router.post("/guardian-links/preview", response_model=schemas.LinkPreviewOut)
def preview_code(body: schemas.AcceptLinkRequest, guardian: sqlite3.Row = Depends(active_user),
                 conn: sqlite3.Connection = Depends(get_db)):
    """§7.1 step 7: the guardian reviews who the code belongs to BEFORE
    approving — this does not consume the code or create the link."""
    if guardian["role"] != "guardian":
        raise ApiError(403, "forbidden", "Only guardian accounts can review link codes.")
    rate_limit.check(f"link-preview:{guardian['id']}", 10)

    code_row = _valid_code_row(conn, body.code)
    user = conn.execute("SELECT display_name, age_band FROM users WHERE id = ?",
                        (code_row["user_id"],)).fetchone()
    if user is None:
        raise ApiError(404, "code_invalid", "This code is not valid or has expired.")
    return {"userName": user["display_name"], "userAgeBand": user["age_band"],
            "expiresAt": code_row["expires_at"]}


@router.post("/guardian-links/accept", response_model=schemas.GuardianLinkOut, status_code=201)
def accept_code(body: schemas.AcceptLinkRequest, guardian: sqlite3.Row = Depends(active_user),
                conn: sqlite3.Connection = Depends(get_db)):
    if guardian["role"] != "guardian":
        raise ApiError(403, "forbidden", "Only guardian accounts can approve link codes.")
    rate_limit.check(f"link-accept:{guardian['id']}", 10)

    code_row = _valid_code_row(conn, body.code)

    existing = conn.execute(
        "SELECT 1 FROM guardian_links WHERE user_id = ? AND guardian_id = ? AND status = 'active'",
        (code_row["user_id"], guardian["id"]),
    ).fetchone()
    if existing:
        raise ApiError(409, "already_linked", "You are already linked to this user.")

    link_id = new_id()
    conn.execute(
        "INSERT INTO guardian_links (id, user_id, guardian_id, status, consented_at)"
        " VALUES (?, ?, ?, 'active', ?)",
        (link_id, code_row["user_id"], guardian["id"], now_iso()),
    )
    conn.execute("UPDATE guardian_link_codes SET consumed_at = ? WHERE id = ?",
                 (now_iso(), code_row["id"]))
    conn.execute("UPDATE users SET status = 'active' WHERE id = ? AND status = 'pending_guardian'",
                 (code_row["user_id"],))
    audit(conn, guardian["id"], "guardian_link_approved", "guardian_links", link_id)

    link = conn.execute("SELECT * FROM guardian_links WHERE id = ?", (link_id,)).fetchone()
    return _link_out(conn, link)


@router.get("/guardian-links", response_model=list[schemas.GuardianLinkOut])
def list_links(user: sqlite3.Row = Depends(current_user),
               conn: sqlite3.Connection = Depends(get_db)):
    if user["role"] == "guardian":
        rows = conn.execute(
            "SELECT * FROM guardian_links WHERE guardian_id = ? ORDER BY consented_at DESC",
            (user["id"],)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM guardian_links WHERE user_id = ? ORDER BY consented_at DESC",
            (user["id"],)).fetchall()
    return [_link_out(conn, row) for row in rows]


@router.delete("/guardian-links/{link_id}", status_code=204)
def revoke_link(link_id: str, user: sqlite3.Row = Depends(current_user),
                conn: sqlite3.Connection = Depends(get_db)):
    link = conn.execute(
        "SELECT * FROM guardian_links WHERE id = ? AND (user_id = ? OR guardian_id = ?)",
        (link_id, user["id"], user["id"]),
    ).fetchone()
    if link is None:
        raise ApiError(404, "not_found", "This link is not available.")
    if link["status"] == "active":
        conn.execute("UPDATE guardian_links SET status = 'revoked', revoked_at = ? WHERE id = ?",
                     (now_iso(), link_id))
        # The guardian's visibility ends with the link, so their alert previews
        # (which carry the user's name and case severity) go too.
        conn.execute(
            "DELETE FROM alerts WHERE recipient_id = ? AND case_id IN ("
            "SELECT id FROM flagged_cases WHERE owner_id = ?)",
            (link["guardian_id"], link["user_id"]),
        )
        audit(conn, user["id"], "guardian_link_revoked", "guardian_links", link_id)


@router.get("/organizations", response_model=list[schemas.OrganizationOut])
def list_organizations(user: sqlite3.Row = Depends(active_user),
                       conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT id, name FROM organizations WHERE status = 'active' ORDER BY name").fetchall()
    return [{"id": r["id"], "name": r["name"]} for r in rows]


def _require_org_admin(conn: sqlite3.Connection, user: sqlite3.Row, org_id: str) -> None:
    # A suspended membership grants nothing: the status column is the control,
    # so it is filtered here and in deps.case_scope, not merely displayed.
    member = conn.execute(
        "SELECT 1 FROM organization_memberships"
        " WHERE organization_id = ? AND user_id = ? AND status = 'active'",
        (org_id, user["id"]),
    ).fetchone()
    if user["role"] != "school_admin" or member is None:
        raise ApiError(403, "forbidden", "Only administrators of this organization can do this.")


@router.get("/organizations/{org_id}/members", response_model=list[schemas.MemberOut])
def list_members(org_id: str, user: sqlite3.Row = Depends(active_user),
                 conn: sqlite3.Connection = Depends(get_db)):
    _require_org_admin(conn, user, org_id)
    rows = conn.execute(
        "SELECT u.id, u.display_name, u.email, m.org_role, m.status"
        " FROM organization_memberships m"
        " JOIN users u ON u.id = m.user_id WHERE m.organization_id = ? ORDER BY u.display_name",
        (org_id,),
    ).fetchall()
    return [{"id": r["id"], "displayName": r["display_name"], "email": r["email"],
             "orgRole": r["org_role"], "status": r["status"]} for r in rows]


@router.post("/organizations/{org_id}/members", response_model=schemas.MemberOut, status_code=201)
def add_member(org_id: str, body: schemas.AddMemberRequest,
               user: sqlite3.Row = Depends(active_user),
               conn: sqlite3.Connection = Depends(get_db)):
    _require_org_admin(conn, user, org_id)
    rate_limit.check(f"member-add:{user['id']}", 10)

    target = conn.execute("SELECT * FROM users WHERE email = ?", (body.email,)).fetchone()
    if target is None:
        raise ApiError(404, "not_found", "No account uses this email address.")
    if target["role"] != "school_admin":
        raise ApiError(409, "not_admin_account",
                       "Only school administrator accounts can join an organization.")
    if conn.execute(
        "SELECT 1 FROM organization_memberships WHERE organization_id = ? AND user_id = ?",
        (org_id, target["id"]),
    ).fetchone():
        raise ApiError(409, "already_member", "This account is already a member.")

    conn.execute(
        "INSERT INTO organization_memberships (id, organization_id, user_id, org_role, status,"
        " created_at) VALUES (?, ?, ?, 'admin', 'active', ?)",
        (new_id(), org_id, target["id"], now_iso()),
    )
    audit(conn, user["id"], "membership_added", "organization_memberships", target["id"])
    return {"id": target["id"], "displayName": target["display_name"],
            "email": target["email"], "orgRole": "admin", "status": "active"}


@router.delete("/organizations/{org_id}/members/{member_id}", status_code=204)
def remove_member(org_id: str, member_id: str, user: sqlite3.Row = Depends(active_user),
                  conn: sqlite3.Connection = Depends(get_db)):
    _require_org_admin(conn, user, org_id)
    if member_id == user["id"]:
        raise ApiError(409, "cannot_remove_self", "You cannot remove your own membership.")
    conn.execute(
        "DELETE FROM organization_memberships WHERE organization_id = ? AND user_id = ?",
        (org_id, member_id),
    )
    # Remove the ex-member's alerts for cases they could only see through this
    # organization's shares (keep alerts they still deserve as an owner or via
    # a remaining membership).
    conn.execute(
        """
        DELETE FROM alerts WHERE recipient_id = :member_id
          AND case_id IN (
            SELECT case_id FROM case_shares
            WHERE organization_id = :org_id AND revoked_at IS NULL)
          AND case_id NOT IN (
            SELECT id FROM flagged_cases WHERE owner_id = :member_id)
          AND case_id NOT IN (
            SELECT cs.case_id FROM case_shares cs
            JOIN organization_memberships m ON m.organization_id = cs.organization_id
            WHERE m.user_id = :member_id AND cs.revoked_at IS NULL
              AND m.status = 'active')
        """,
        {"member_id": member_id, "org_id": org_id},
    )
    audit(conn, user["id"], "membership_removed", "organization_memberships", member_id)
