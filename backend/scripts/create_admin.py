"""Create a School Administrator account bound to one organization.

School Administrator accounts are invitation-only: the public registration
endpoint refuses the role, so this local command is the only way to make one.

    conda activate a-mbl
    python -m backend.scripts.create_admin "Greenfield School" admin@school.test "a-strong-password" "Ms. Haddad"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import security  # noqa: E402
from backend.app.db import audit, connect, new_id, now_iso  # noqa: E402


def create_admin(org_name: str, email: str, password: str, display_name: str) -> None:
    email = email.strip().lower()
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")

    conn = connect()
    try:
        org = conn.execute("SELECT * FROM organizations WHERE name = ?", (org_name,)).fetchone()
        if org is None:
            org_id = new_id()
            conn.execute(
                "INSERT INTO organizations (id, name, status, created_at) VALUES (?, ?, 'active', ?)",
                (org_id, org_name, now_iso()),
            )
        else:
            org_id = org["id"]

        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise SystemExit(f"An account with email {email} already exists.")

        user_id = new_id()
        conn.execute(
            "INSERT INTO users (id, email, password_hash, display_name, role, age_band, status, created_at)"
            " VALUES (?, ?, ?, ?, 'school_admin', '18+', 'active', ?)",
            (user_id, email, security.hash_password(password), display_name.strip(), now_iso()),
        )
        conn.execute(
            "INSERT INTO organization_memberships (id, organization_id, user_id, org_role, created_at)"
            " VALUES (?, ?, ?, 'admin', ?)",
            (new_id(), org_id, user_id, now_iso()),
        )
        audit(conn, None, "school_admin_created", "users", user_id)
        conn.commit()
    finally:
        conn.close()
    print(f"School Administrator '{display_name}' created for organization '{org_name}'.")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit(
            'Usage: python -m backend.scripts.create_admin "Org name" email password "Display name"')
    create_admin(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
