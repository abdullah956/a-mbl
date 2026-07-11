"""30-day retention cleanup, data export, and account deletion."""

from backend.app import config, retention


def test_expired_cases_are_hidden_then_deleted(client, register, analyze, auth, db, png_bytes):
    session = register("retention@test.io")
    case_id = analyze(session, "i will kill you")["caseId"]
    client.post(f"/v1/cases/{case_id}/evidence",
                files={"file": ("shot.png", png_bytes(), "image/png")}, headers=auth(session))
    assert len(list((config.data_dir() / "evidence").iterdir())) == 1

    with db() as conn:
        conn.execute("UPDATE flagged_cases SET expires_at = '2020-01-01T00:00:00+00:00'")
        conn.commit()

    # Hidden from every endpoint even before the cleanup job runs.
    assert client.get(f"/v1/cases/{case_id}", headers=auth(session)).status_code == 404
    assert client.get("/v1/cases", headers=auth(session)).json()["total"] == 0

    with db() as conn:
        result = retention.cleanup(conn)
        assert result["casesRemoved"] == 1
        assert conn.execute("SELECT COUNT(*) AS n FROM flagged_cases").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM alerts").fetchone()["n"] == 0
    assert list((config.data_dir() / "evidence").iterdir()) == []


def test_cleanup_purges_stale_codes_and_tokens(client, register_teen, db):
    register_teen()
    with db() as conn:
        conn.execute("UPDATE guardian_link_codes SET expires_at = '2020-01-01T00:00:00+00:00'")
        conn.execute("UPDATE refresh_tokens SET expires_at = '2020-01-01T00:00:00+00:00'")
        conn.commit()
        result = retention.cleanup(conn)
    assert result["codesRemoved"] == 1
    assert result["tokensRemoved"] == 1


def test_export_contains_own_decrypted_cases_only(client, make_linked_pair, analyze, auth):
    teen, guardian = make_linked_pair()
    analyze(teen, "i will kill you")

    teen_export = client.get("/v1/privacy/export", headers=auth(teen)).json()
    assert teen_export["profile"]["email"] == "teen@test.io"
    assert len(teen_export["cases"]) == 1
    assert "kill you" in teen_export["cases"][0]["text"]

    # The guardian's export includes the link but not the teen's content.
    guardian_export = client.get("/v1/privacy/export", headers=auth(guardian)).json()
    assert guardian_export["cases"] == []
    assert len(guardian_export["guardianLinks"]) == 1


def test_guardian_account_deletion_keeps_teen_case(client, make_linked_pair, analyze, auth):
    from .conftest import PASSWORD

    teen, guardian = make_linked_pair()
    case_id = analyze(teen, "i will kill you")["caseId"]
    client.post(f"/v1/cases/{case_id}/reviews", json={"note": "Checked with the school."},
                headers=auth(guardian))

    deleted = client.request("DELETE", "/v1/privacy/account",
                             json={"password": PASSWORD}, headers=auth(guardian))
    assert deleted.status_code == 204

    # The teen's case survives; the deleted reviewer's rows cascade away.
    detail = client.get(f"/v1/cases/{case_id}", headers=auth(teen))
    assert detail.status_code == 200
    assert detail.json()["reviews"] == []
    assert detail.json()["status"] == "reviewed"


def test_account_deletion_requires_password_and_removes_everything(
        client, register, analyze, auth, db, png_bytes):
    from .conftest import PASSWORD

    session = register("gone@test.io")
    case_id = analyze(session, "i will kill you")["caseId"]
    client.post(f"/v1/cases/{case_id}/evidence",
                files={"file": ("shot.png", png_bytes(), "image/png")}, headers=auth(session))

    wrong = client.request("DELETE", "/v1/privacy/account",
                           json={"password": "not-the-password"}, headers=auth(session))
    assert wrong.status_code == 401

    deleted = client.request("DELETE", "/v1/privacy/account",
                             json={"password": PASSWORD}, headers=auth(session))
    assert deleted.status_code == 204

    login = client.post("/v1/auth/login", json={"email": "gone@test.io", "password": PASSWORD})
    assert login.status_code == 401

    with db() as conn:
        for table in ("users", "flagged_cases", "analysis_events", "refresh_tokens",
                      "case_evidence", "alerts"):
            assert conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] == 0, table
    assert list((config.data_dir() / "evidence").iterdir()) == []
