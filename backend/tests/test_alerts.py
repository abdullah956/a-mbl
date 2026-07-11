"""Risk-tiered in-app alerts: creation rules, scoping, previews, dedupe."""


def test_threat_alerts_owner_and_linked_guardian(client, make_linked_pair, analyze, auth):
    teen, guardian = make_linked_pair()
    result = analyze(teen, "i will kill you")
    assert result["severity"] == "critical"

    teen_alerts = client.get("/v1/alerts", headers=auth(teen)).json()
    guardian_alerts = client.get("/v1/alerts", headers=auth(guardian)).json()
    assert len(teen_alerts) == 1
    assert len(guardian_alerts) == 1
    assert guardian_alerts[0]["caseId"] == result["caseId"]
    assert guardian_alerts[0]["subjectName"] == teen["user"]["displayName"]


def test_alert_preview_contains_no_raw_content(client, make_linked_pair, analyze, auth):
    teen, guardian = make_linked_pair()
    marker = "zebraAlertMarker"
    analyze(teen, f"i will kill you at {marker}")

    alerts = client.get("/v1/alerts", headers=auth(guardian)).json()
    body = str(alerts)
    assert marker not in body
    assert set(alerts[0].keys()) == {"id", "caseId", "severity", "primaryLabel",
                                     "subjectName", "createdAt", "readAt"}


def test_offensive_results_do_not_alert(client, make_linked_pair, analyze, auth):
    teen, guardian = make_linked_pair()
    result = analyze(teen, "you are an idiot")
    assert result["caseId"]  # case exists
    assert client.get("/v1/alerts", headers=auth(guardian)).json() == []
    assert client.get("/v1/alerts", headers=auth(teen)).json() == []


def test_unlinked_guardian_gets_no_alerts(client, register, register_teen, analyze, auth):
    guardian = register("unlinked@test.io", role="guardian", year=1980)
    owner = register("solo@test.io")
    analyze(owner, "i will kill you")
    assert client.get("/v1/alerts", headers=auth(guardian)).json() == []


def test_share_alerts_org_admins_and_revoke_removes(client, register, analyze,
                                                    make_admin, auth):
    owner = register("owner@test.io")
    admin = make_admin()
    case_id = analyze(owner, "i will kill you")["caseId"]

    assert client.get("/v1/alerts", headers=auth(admin)).json() == []
    org_id = client.get("/v1/organizations", headers=auth(owner)).json()[0]["id"]
    share = client.post(f"/v1/cases/{case_id}/shares", json={"organizationId": org_id},
                        headers=auth(owner)).json()

    admin_alerts = client.get("/v1/alerts", headers=auth(admin)).json()
    assert len(admin_alerts) == 1

    client.delete(f"/v1/cases/{case_id}/shares/{share['id']}", headers=auth(owner))
    assert client.get("/v1/alerts", headers=auth(admin)).json() == []


def test_duplicate_alert_creation_is_deduplicated(client, register, analyze, auth, db):
    from backend.app.routers.analysis import create_alerts_for_case

    owner = register("owner@test.io")
    case_id = analyze(owner, "i will kill you")["caseId"]

    with db() as conn:
        case = conn.execute("SELECT * FROM flagged_cases WHERE id = ?", (case_id,)).fetchone()
        create_alerts_for_case(conn, case, [owner["user"]["id"]])
        create_alerts_for_case(conn, case, [owner["user"]["id"]])
        conn.commit()
        count = conn.execute("SELECT COUNT(*) AS n FROM alerts WHERE case_id = ?",
                             (case_id,)).fetchone()["n"]
    assert count == 1


def test_link_revocation_removes_guardian_alerts(client, make_linked_pair, analyze, auth):
    teen, guardian = make_linked_pair()
    analyze(teen, "i will kill you")
    assert len(client.get("/v1/alerts", headers=auth(guardian)).json()) == 1

    link_id = client.get("/v1/guardian-links", headers=auth(guardian)).json()[0]["id"]
    client.delete(f"/v1/guardian-links/{link_id}", headers=auth(guardian))

    assert client.get("/v1/alerts", headers=auth(guardian)).json() == []
    assert len(client.get("/v1/alerts", headers=auth(teen)).json()) == 1  # owner keeps theirs


def test_mark_alert_read_and_scoping(client, register, analyze, auth):
    owner = register("owner@test.io")
    other = register("other@test.io")
    analyze(owner, "i will kill you")

    alert = client.get("/v1/alerts", headers=auth(owner)).json()[0]
    assert alert["readAt"] is None

    marked = client.patch(f"/v1/alerts/{alert['id']}", json={"read": True}, headers=auth(owner))
    assert marked.json()["readAt"] is not None

    foreign = client.patch(f"/v1/alerts/{alert['id']}", json={"read": True}, headers=auth(other))
    assert foreign.status_code == 404
