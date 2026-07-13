"""Authentication dependencies and role-scoped case visibility.

Case visibility (roadmap §5.4): owners see their own cases; guardians also see
cases of users linked by an ACTIVE guardian link; school administrators also
see cases explicitly shared (and not revoked) with an organization they belong
to. These rules are applied in SQL before any row is serialized.
"""

import sqlite3

from fastapi import Depends, Header

from . import security
from .db import get_db, now_iso
from .errors import ApiError


def _load_user(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def current_user(
    authorization: str = Header(default=""),
    conn: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row:
    if not authorization.startswith("Bearer "):
        raise ApiError(401, "unauthorized", "Sign in to continue.")
    user_id = security.read_access_token(authorization.removeprefix("Bearer ").strip())
    user = _load_user(conn, user_id) if user_id else None
    if user is None:
        raise ApiError(401, "unauthorized", "Your session has expired. Sign in again.")
    return user


def active_user(user: sqlite3.Row = Depends(current_user)) -> sqlite3.Row:
    if user["status"] != "active":
        raise ApiError(403, "account_pending",
                       "This account is waiting for guardian approval.")
    return user


def user_organizations(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT o.id, o.name FROM organizations o"
        " JOIN organization_memberships m ON m.organization_id = o.id"
        " WHERE m.user_id = ? AND m.status = 'active' AND o.status = 'active'",
        (user_id,),
    ).fetchall()
    return [{"id": r["id"], "name": r["name"]} for r in rows]


def permissions_for(user: sqlite3.Row) -> dict:
    """What this account may do (roadmap §10.1: /v1/me returns the profile AND
    permissions). Advisory only — the SQL scope in case_scope is the real
    control; these flags exist so screens do not have to re-derive role rules."""
    role, active = user["role"], user["status"] == "active"
    return {
        "canAnalyze": active,
        "canCreateLinkCode": active and role == "user",
        "canApproveLinkCode": active and role == "guardian",
        "canShareCases": active and role == "user",
        "canManageMembers": active and role == "school_admin",
    }


def user_out(conn: sqlite3.Connection, user: sqlite3.Row) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "displayName": user["display_name"],
        "role": user["role"],
        "ageBand": user["age_band"],
        "status": user["status"],
        "createdAt": user["created_at"],
        "organizations": user_organizations(conn, user["id"]),
        "permissions": permissions_for(user),
    }


def case_scope(user: sqlite3.Row) -> tuple[str, list]:
    """WHERE fragment limiting flagged_cases rows (aliased fc) to this user's
    visibility. Also excludes expired cases as a belt-and-braces filter."""
    base = "fc.expires_at > ? AND "
    params: list = [now_iso()]
    if user["role"] == "guardian":
        clause = ("(fc.owner_id = ? OR fc.owner_id IN ("
                  "SELECT user_id FROM guardian_links WHERE guardian_id = ? AND status = 'active'))")
        params += [user["id"], user["id"]]
    elif user["role"] == "school_admin":
        clause = ("(fc.owner_id = ? OR fc.id IN ("
                  "SELECT case_id FROM case_shares WHERE revoked_at IS NULL AND organization_id IN ("
                  "SELECT organization_id FROM organization_memberships"
                  " WHERE user_id = ? AND status = 'active')))")
        params += [user["id"], user["id"]]
    else:
        clause = "fc.owner_id = ?"
        params += [user["id"]]
    return base + clause, params


def load_case(conn: sqlite3.Connection, user: sqlite3.Row, case_id: str) -> sqlite3.Row:
    """Return the case row if visible to this user, else 404 (existence is not
    revealed to unauthorized accounts)."""
    scope_sql, params = case_scope(user)
    row = conn.execute(
        f"SELECT fc.* FROM flagged_cases fc WHERE fc.id = ? AND {scope_sql}",
        [case_id] + params,
    ).fetchone()
    if row is None:
        raise ApiError(404, "not_found", "This case is not available.")
    return row


def require_case_owner(user: sqlite3.Row, case: sqlite3.Row) -> None:
    if case["owner_id"] != user["id"]:
        raise ApiError(403, "forbidden", "Only the case owner can do this.")
