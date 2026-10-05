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


def test_alert_shows_the_owners_current_name(client, make_linked_pair, analyze, auth):
    teen, guardian = make_linked_pair()
    analyze(teen, "i will kill you")
    client.patch("/v1/me", json={"displayName": "Renamed Teen"}, headers=auth(teen))

    alerts = client.get("/v1/alerts", headers=auth(guardian)).json()
    assert alerts[0]["subjectName"] == "Renamed Teen"


def test_unshare_removes_alert_of_member_whose_other_membership_is_suspended(
        client, register, analyze, make_admin, auth, db):
    # Admin B belongs to School A and School B. The case is shared with both.
    owner = register("owner@test.io")
    admin_a = make_admin(org="School A", email="a@test.io")
    admin_b = make_admin(org="School B", email="b@test.io")
    org_a = admin_a["user"]["organizations"][0]["id"]
    org_b = admin_b["user"]["organizations"][0]["id"]
    client.post(f"/v1/organizations/{org_a}/members", json={"email": "b@test.io"},
                headers=auth(admin_a))

    case_id = analyze(owner, "i will kill you")["caseId"]
    share_a = client.post(f"/v1/cases/{case_id}/shares", json={"organizationId": org_a},
                          headers=auth(owner)).json()
    client.post(f"/v1/cases/{case_id}/shares", json={"organizationId": org_b},
                headers=auth(owner))
    assert len(client.get("/v1/alerts", headers=auth(admin_b)).json()) == 1

    # A suspended School B membership grants nothing, so once School A's share
    # is revoked, admin B no longer has any right to the alert.
    with db() as conn:
        conn.execute("UPDATE organization_memberships SET status = 'suspended'"
                     " WHERE organization_id = ? AND user_id = ?",
                     (org_b, admin_b["user"]["id"]))
        conn.commit()
    client.delete(f"/v1/cases/{case_id}/shares/{share_a['id']}", headers=auth(owner))
    assert client.get("/v1/alerts", headers=auth(admin_b)).json() == []


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
