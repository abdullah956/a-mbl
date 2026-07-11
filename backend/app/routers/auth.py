"""Registration, login, token rotation, and profile (roadmap §7.1, §10.1).

Age screening happens before the account exists: under-13 registration is
refused neutrally and stores nothing. Only the age band is kept — never the
birth month/year. `school_admin` is not a public registration role.
"""

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends

from .. import config, rate_limit, security, schemas
from ..db import audit, get_db, in_future, new_id, now_iso
from ..deps import current_user, user_out
from ..errors import ApiError

router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(tags=["me"])


def _age_band(birth_year: int, birth_month: int) -> str | None:
    today = date.today()
    age = today.year - birth_year - (1 if today.month < birth_month else 0)
    if age < 13:
        return None
    return "13-17" if age < 18 else "18+"


def _issue_tokens(conn: sqlite3.Connection, user_id: str) -> tuple[str, str]:
    refresh = security.new_refresh_token()
    conn.execute(
        "INSERT INTO refresh_tokens (id, token_hash, user_id, expires_at) VALUES (?, ?, ?, ?)",
        (new_id(), security.sha256_hex(refresh), user_id,
         in_future(days=config.REFRESH_TOKEN_DAYS)),
    )
    return security.make_access_token(user_id), refresh


def _create_link_code(conn: sqlite3.Connection, user_id: str) -> tuple[str, str]:
    code = security.new_link_code()
    expires = in_future(hours=config.GUARDIAN_CODE_HOURS)
    conn.execute(
        "INSERT INTO guardian_link_codes (id, code_hash, user_id, expires_at) VALUES (?, ?, ?, ?)",
        (new_id(), security.sha256_hex(code), user_id, expires),
    )
    return code, expires


@router.post("/register", response_model=schemas.AuthResponse, status_code=201)
def register(body: schemas.RegisterRequest, conn: sqlite3.Connection = Depends(get_db)):
    rate_limit.check(f"register:{body.email}", 5)

    band = _age_band(body.birthYear, body.birthMonth)
    if band is None:
        raise ApiError(403, "age_not_supported",
                       "This app supports ages 13 and above. No account was created.")
    if body.role == "guardian" and band != "18+":
        raise ApiError(403, "guardian_must_be_adult", "Guardian accounts must be 18 or older.")

    if conn.execute("SELECT 1 FROM users WHERE email = ?", (body.email,)).fetchone():
        raise ApiError(409, "email_in_use", "An account with this email already exists.")

    status = "pending_guardian" if body.role == "user" and band == "13-17" else "active"
    user_id = new_id()
    conn.execute(
        "INSERT INTO users (id, email, password_hash, display_name, role, age_band, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, body.email, security.hash_password(body.password), body.displayName.strip(),
         body.role, band, status, now_iso()),
    )
    audit(conn, user_id, "user_registered", "users", user_id)

    link_code = expires = None
    if status == "pending_guardian":
        link_code, expires = _create_link_code(conn, user_id)

    access, refresh = _issue_tokens(conn, user_id)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return {"accessToken": access, "refreshToken": refresh, "user": user_out(conn, user),
            "linkCode": link_code, "linkCodeExpiresAt": expires}


@router.post("/login", response_model=schemas.AuthResponse)
def login(body: schemas.LoginRequest, conn: sqlite3.Connection = Depends(get_db)):
    email = body.email.strip().lower()
    rate_limit.check(f"login:{email}", 8)

    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is None or not security.verify_password(body.password, user["password_hash"]):
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")

    access, refresh = _issue_tokens(conn, user["id"])
    audit(conn, user["id"], "user_login", "users", user["id"])
    return {"accessToken": access, "refreshToken": refresh, "user": user_out(conn, user)}


@router.post("/refresh", response_model=schemas.AuthResponse)
def refresh(body: schemas.RefreshRequest, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute(
        "SELECT * FROM refresh_tokens WHERE token_hash = ?",
        (security.sha256_hex(body.refreshToken),),
    ).fetchone()
    if row is None:
        raise ApiError(401, "invalid_refresh", "Sign in again to continue.")
    if row["revoked_at"] is not None:
        # Reuse of a rotated token: revoke every session for this account.
        conn.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (now_iso(), row["user_id"]),
        )
        audit(conn, row["user_id"], "refresh_reuse_detected", "refresh_tokens", row["id"])
        conn.commit()  # persist the revocation even though this request errors
        raise ApiError(401, "invalid_refresh", "Sign in again to continue.")
    if row["expires_at"] <= now_iso():
        raise ApiError(401, "invalid_refresh", "Sign in again to continue.")

    user = conn.execute("SELECT * FROM users WHERE id = ?", (row["user_id"],)).fetchone()
    access, new_refresh = _issue_tokens(conn, user["id"])
    new_row = conn.execute(
        "SELECT id FROM refresh_tokens WHERE token_hash = ?",
        (security.sha256_hex(new_refresh),),
    ).fetchone()
    conn.execute(
        "UPDATE refresh_tokens SET revoked_at = ?, replaced_by = ? WHERE id = ?",
        (now_iso(), new_row["id"], row["id"]),
    )
    return {"accessToken": access, "refreshToken": new_refresh, "user": user_out(conn, user)}


@router.post("/logout", status_code=204)
def logout(body: schemas.RefreshRequest, conn: sqlite3.Connection = Depends(get_db)):
    # Possession of the refresh token is the credential here: sign-out must
    # work even when the short-lived access token has already expired.
    row = conn.execute(
        "SELECT id, user_id FROM refresh_tokens WHERE token_hash = ? AND revoked_at IS NULL",
        (security.sha256_hex(body.refreshToken),),
    ).fetchone()
    if row is not None:
        conn.execute("UPDATE refresh_tokens SET revoked_at = ? WHERE id = ?",
                     (now_iso(), row["id"]))
        audit(conn, row["user_id"], "user_logout", "users", row["user_id"])


@me_router.get("/me", response_model=schemas.UserOut)
def me(user: sqlite3.Row = Depends(current_user), conn: sqlite3.Connection = Depends(get_db)):
    return user_out(conn, user)


@me_router.patch("/me", response_model=schemas.UserOut)
def patch_me(body: schemas.PatchMeRequest, user: sqlite3.Row = Depends(current_user),
             conn: sqlite3.Connection = Depends(get_db)):
    if body.displayName is not None:
        conn.execute("UPDATE users SET display_name = ? WHERE id = ?",
                     (body.displayName.strip(), user["id"]))
    fresh = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return user_out(conn, fresh)
