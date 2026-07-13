"""SQLite access with the schema created on first connection.

Plain sqlite3 keeps the prototype simple: one file, foreign keys enabled,
ISO-8601 UTC strings for timestamps, uuid4 hex strings for ids.
"""

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'guardian', 'school_admin')),
    age_band TEXT NOT NULL CHECK (age_band IN ('13-17', '18+')),
    status TEXT NOT NULL CHECK (status IN ('pending_guardian', 'active')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS organization_memberships (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_role TEXT NOT NULL DEFAULT 'admin',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    UNIQUE (organization_id, user_id)
);

CREATE TABLE IF NOT EXISTS guardian_links (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    guardian_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
    consented_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS guardian_link_codes (
    id TEXT PRIMARY KEY,
    code_hash TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    consumed_at TEXT
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    replaced_by TEXT
);

-- One row per analysis. Raw submitted text is NEVER stored here.
CREATE TABLE IF NOT EXISTS analysis_events (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (source_type IN ('text', 'screenshot')),
    primary_label TEXT NOT NULL,
    confidence REAL NOT NULL,
    body_shaming INTEGER NOT NULL DEFAULT 0,
    severity TEXT NOT NULL,
    needs_review INTEGER NOT NULL DEFAULT 0,
    model_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Harmful results only. Confirmed text is stored encrypted and expires.
CREATE TABLE IF NOT EXISTS flagged_cases (
    id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL UNIQUE REFERENCES analysis_events(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    encrypted_text BLOB NOT NULL,
    platform_name TEXT,
    sender_alias TEXT,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'reviewed')),
    review_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_evidence (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES flagged_cases(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_shares (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES flagged_cases(id) ON DELETE CASCADE,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    shared_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    shared_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS review_events (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES flagged_cases(id) ON DELETE CASCADE,
    reviewer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    human_label TEXT,
    encrypted_note BLOB,
    created_at TEXT NOT NULL
);

-- Alert previews must never contain raw content.
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    recipient_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    case_id TEXT NOT NULL REFERENCES flagged_cases(id) ON DELETE CASCADE,
    severity TEXT NOT NULL,
    primary_label TEXT NOT NULL,
    subject_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT,
    UNIQUE (recipient_id, case_id)
);

-- §11: artifact checksum, label map and metrics stay NULL for the lexicon
-- baseline (no artifact, no measured metrics) and are filled by the trained
-- model when it lands — the swap-in must not require a schema change.
CREATE TABLE IF NOT EXISTS model_versions (
    version TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    thresholds_json TEXT NOT NULL,
    artifact_checksum TEXT,
    label_map_json TEXT,
    metrics_json TEXT,
    created_at TEXT NOT NULL
);

-- Audit rows never contain raw content or secrets.
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    actor_id TEXT,
    action TEXT NOT NULL,
    object_type TEXT,
    object_id TEXT,
    created_at TEXT NOT NULL
);
"""


# Columns added after a table already shipped: CREATE TABLE IF NOT EXISTS
# cannot alter an existing database, so each is retried as an ALTER and the
# "duplicate column" error on fresh databases is expected and ignored.
_MIGRATIONS = (
    "ALTER TABLE flagged_cases ADD COLUMN review_requested INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE organization_memberships ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
    "ALTER TABLE model_versions ADD COLUMN artifact_checksum TEXT",
    "ALTER TABLE model_versions ADD COLUMN label_map_json TEXT",
    "ALTER TABLE model_versions ADD COLUMN metrics_json TEXT",
)


def connect() -> sqlite3.Connection:
    # check_same_thread=False: FastAPI may run the dependency and the endpoint
    # on different threadpool threads; each request still uses one connection
    # sequentially, which is safe.
    conn = sqlite3.connect(config.db_path(), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    for statement in _MIGRATIONS:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError:
            pass
    return conn


def get_db():
    """FastAPI dependency: one connection per request."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def new_id() -> str:
    return uuid.uuid4().hex


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def now_iso() -> str:
    return iso(utc_now())


def in_future(**delta) -> str:
    return iso(utc_now() + timedelta(**delta))


def audit(conn: sqlite3.Connection, actor_id: str | None, action: str,
          object_type: str | None = None, object_id: str | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_events (id, actor_id, action, object_type, object_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (new_id(), actor_id, action, object_type, object_id, now_iso()),
    )
