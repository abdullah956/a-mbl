"""Role-scoped case access, human review, evidence, and organization shares."""


def test_owner_lists_and_filters_cases(client, register, analyze, auth):
    session = register("owner@test.io")
    analyze(session, "you are an idiot")
    analyze(session, "i will kill you")
    analyze(session, "have a great day")  # normal, no case

    listing = client.get("/v1/cases", headers=auth(session)).json()
    assert listing["total"] == 2

    critical_only = client.get("/v1/cases?severity=critical", headers=auth(session)).json()
    assert critical_only["total"] == 1
    assert critical_only["items"][0]["primaryLabel"] == "threat"


def test_case_idor_protection(client, register, analyze, auth):
    owner = register("owner@test.io")
    stranger = register("stranger@test.io")
    case_id = analyze(owner, "i will kill you")["caseId"]

    assert client.get(f"/v1/cases/{case_id}", headers=auth(stranger)).status_code == 404
    assert client.patch(f"/v1/cases/{case_id}", json={"platformName": "X"},
                        headers=auth(stranger)).status_code == 404
    assert client.delete(f"/v1/cases/{case_id}", headers=auth(stranger)).status_code == 404
    assert client.get("/v1/cases", headers=auth(stranger)).json()["total"] == 0


def test_guardian_sees_linked_cases_until_revoked(client, make_linked_pair, analyze, auth):
    teen, guardian = make_linked_pair()
    case_id = analyze(teen, "everyone hates you, watch your back")["caseId"]

    listing = client.get("/v1/cases", headers=auth(guardian)).json()
    assert listing["total"] == 1
    assert listing["items"][0]["isOwn"] is False
    detail = client.get(f"/v1/cases/{case_id}", headers=auth(guardian))
    assert detail.status_code == 200

    link_id = client.get("/v1/guardian-links", headers=auth(guardian)).json()[0]["id"]
    client.delete(f"/v1/guardian-links/{link_id}", headers=auth(guardian))

    assert client.get(f"/v1/cases/{case_id}", headers=auth(guardian)).status_code == 404
    assert client.get("/v1/cases", headers=auth(guardian)).json()["total"] == 0


def test_admin_sees_only_explicitly_shared_cases(client, register, analyze, make_admin, auth):
    owner = register("owner@test.io")
    admin = make_admin()
    case_id = analyze(owner, "i will kill you")["caseId"]

    # Not shared yet: invisible.
    assert client.get(f"/v1/cases/{case_id}", headers=auth(admin)).status_code == 404

    org_id = client.get("/v1/organizations", headers=auth(owner)).json()[0]["id"]
    share = client.post(f"/v1/cases/{case_id}/shares", json={"organizationId": org_id},
                        headers=auth(owner))
    assert share.status_code == 201

    assert client.get(f"/v1/cases/{case_id}", headers=auth(admin)).status_code == 200

    # Revoking the share removes access immediately.
    share_id = share.json()["id"]
    revoke = client.delete(f"/v1/cases/{case_id}/shares/{share_id}", headers=auth(owner))
    assert revoke.status_code == 204
    assert client.get(f"/v1/cases/{case_id}", headers=auth(admin)).status_code == 404


def test_admin_from_other_org_sees_nothing(client, register, analyze, make_admin, auth):
    owner = register("owner@test.io")
    admin_a = make_admin(org="School A", email="a@test.io")
    admin_b = make_admin(org="School B", email="b@test.io")
    case_id = analyze(owner, "i will kill you")["caseId"]

    orgs = client.get("/v1/organizations", headers=auth(owner)).json()
    org_a = next(o for o in orgs if o["name"] == "School A")
    client.post(f"/v1/cases/{case_id}/shares", json={"organizationId": org_a["id"]},
                headers=auth(owner))

    assert client.get(f"/v1/cases/{case_id}", headers=auth(admin_a)).status_code == 200
    assert client.get(f"/v1/cases/{case_id}", headers=auth(admin_b)).status_code == 404


def test_duplicate_share_conflicts(client, register, analyze, make_admin, auth):
    owner = register("owner@test.io")
    make_admin()
    case_id = analyze(owner, "i will kill you")["caseId"]
    org_id = client.get("/v1/organizations", headers=auth(owner)).json()[0]["id"]

    first = client.post(f"/v1/cases/{case_id}/shares", json={"organizationId": org_id},
                        headers=auth(owner))
    second = client.post(f"/v1/cases/{case_id}/shares", json={"organizationId": org_id},
                         headers=auth(owner))
    assert first.status_code == 201
    assert second.status_code == 409


def test_review_does_not_change_model_output(client, make_linked_pair, analyze, auth):
    teen, guardian = make_linked_pair()
    case_id = analyze(teen, "nobody likes you, loser")["caseId"]

    review = client.post(f"/v1/cases/{case_id}/reviews",
                         json={"humanLabel": "offensive", "note": "Looks like a one-off insult."},
                         headers=auth(guardian))
    assert review.status_code == 201

    detail = client.get(f"/v1/cases/{case_id}", headers=auth(teen)).json()
    assert detail["primaryLabel"] == "harassment"  # immutable model output
    assert detail["status"] == "reviewed"
    assert detail["reviews"][0]["humanLabel"] == "offensive"
    assert detail["reviews"][0]["reviewerRole"] == "guardian"
    assert "one-off insult" in detail["reviews"][0]["note"]


def test_review_requires_label_or_note(client, register, analyze, auth):
    owner = register("owner@test.io")
    case_id = analyze(owner, "i will kill you")["caseId"]
    response = client.post(f"/v1/cases/{case_id}/reviews", json={}, headers=auth(owner))
    assert response.status_code == 422


def test_evidence_attach_fetch_and_single_slot(client, register, analyze, auth, png_bytes):
    owner = register("owner@test.io")
    stranger = register("stranger@test.io")
    case_id = analyze(owner, "i will kill you")["caseId"]

    upload = client.post(f"/v1/cases/{case_id}/evidence",
                         files={"file": ("shot.png", png_bytes(), "image/png")},
                         headers=auth(owner))
    assert upload.status_code == 201
    evidence_id = upload.json()["id"]

    again = client.post(f"/v1/cases/{case_id}/evidence",
                        files={"file": ("shot.png", png_bytes(), "image/png")},
                        headers=auth(owner))
    assert again.status_code == 409

    fetched = client.get(f"/v1/cases/{case_id}/evidence/{evidence_id}", headers=auth(owner))
    assert fetched.status_code == 200
    assert fetched.content == png_bytes()
    assert fetched.headers["content-type"] == "image/png"

    forbidden = client.get(f"/v1/cases/{case_id}/evidence/{evidence_id}", headers=auth(stranger))
    assert forbidden.status_code == 404


def test_guardian_evidence_access_ends_with_link(client, make_linked_pair, analyze,
                                                 auth, png_bytes):
    teen, guardian = make_linked_pair()
    case_id = analyze(teen, "i will kill you")["caseId"]
    upload = client.post(f"/v1/cases/{case_id}/evidence",
                         files={"file": ("shot.png", png_bytes(), "image/png")},
                         headers=auth(teen))
    evidence_id = upload.json()["id"]

    allowed = client.get(f"/v1/cases/{case_id}/evidence/{evidence_id}", headers=auth(guardian))
    assert allowed.status_code == 200
    assert allowed.content == png_bytes()

    link_id = client.get("/v1/guardian-links", headers=auth(guardian)).json()[0]["id"]
    client.delete(f"/v1/guardian-links/{link_id}", headers=auth(guardian))
    denied = client.get(f"/v1/cases/{case_id}/evidence/{evidence_id}", headers=auth(guardian))
    assert denied.status_code == 404


def test_oversized_evidence_rejected(client, register, analyze, auth):
    from backend.app import config

    owner = register("bigfile@test.io")
    case_id = analyze(owner, "i will kill you")["caseId"]
    data = b"\xff\xd8\xff" + b"\x00" * config.MAX_IMAGE_BYTES
    response = client.post(f"/v1/cases/{case_id}/evidence",
                           files={"file": ("big.jpg", data, "image/jpeg")},
                           headers=auth(owner))
    assert response.status_code == 413


def test_share_revocation_keeps_owner_and_guardian_alerts(client, make_linked_pair,
                                                          analyze, make_admin, auth):
    teen, guardian = make_linked_pair()
    admin = make_admin()
    case_id = analyze(teen, "i will kill you")["caseId"]
    org_id = client.get("/v1/organizations", headers=auth(teen)).json()[0]["id"]
    share = client.post(f"/v1/cases/{case_id}/shares", json={"organizationId": org_id},
                        headers=auth(teen)).json()
    assert len(client.get("/v1/alerts", headers=auth(admin)).json()) == 1

    client.delete(f"/v1/cases/{case_id}/shares/{share['id']}", headers=auth(teen))
    assert client.get("/v1/alerts", headers=auth(admin)).json() == []
    # Owner and linked guardian keep their alerts — only the org's access ended.
    assert len(client.get("/v1/alerts", headers=auth(teen)).json()) == 1
    assert len(client.get("/v1/alerts", headers=auth(guardian)).json()) == 1


def test_evidence_is_encrypted_on_disk(client, register, analyze, auth, png_bytes):
    from backend.app import config

    owner = register("owner@test.io")
    case_id = analyze(owner, "i will kill you")["caseId"]
    client.post(f"/v1/cases/{case_id}/evidence",
                files={"file": ("shot.png", png_bytes(), "image/png")}, headers=auth(owner))

    stored = list((config.data_dir() / "evidence").iterdir())
    assert len(stored) == 1
    assert stored[0].read_bytes() != png_bytes()          # not the plaintext image
    assert not stored[0].read_bytes().startswith(b"\x89PNG")


def test_delete_case_removes_evidence_file(client, register, analyze, auth, png_bytes):
    from backend.app import config

    owner = register("owner@test.io")
    case_id = analyze(owner, "i will kill you")["caseId"]
    client.post(f"/v1/cases/{case_id}/evidence",
                files={"file": ("shot.png", png_bytes(), "image/png")}, headers=auth(owner))

    assert client.delete(f"/v1/cases/{case_id}", headers=auth(owner)).status_code == 204
    assert client.get(f"/v1/cases/{case_id}", headers=auth(owner)).status_code == 404
    assert list((config.data_dir() / "evidence").iterdir()) == []


def test_only_active_org_members_manage_members(client, register, make_admin, auth):
    admin = make_admin()
    user = register("plain@test.io")
    org_id = admin["user"]["organizations"][0]["id"]

    members = client.get(f"/v1/organizations/{org_id}/members", headers=auth(admin))
    assert members.status_code == 200
    assert len(members.json()) == 1

    denied = client.get(f"/v1/organizations/{org_id}/members", headers=auth(user))
    assert denied.status_code == 403

    self_removal = client.delete(f"/v1/organizations/{org_id}/members/{admin['user']['id']}",
                                 headers=auth(admin))
    assert self_removal.status_code == 409


def test_admin_adds_and_removes_member(client, make_admin, auth):
    admin = make_admin()
    second = make_admin(org="Other School", email="admin2@test.io", name="Second Admin")
    org_id = admin["user"]["organizations"][0]["id"]

    added = client.post(f"/v1/organizations/{org_id}/members",
                        json={"email": "admin2@test.io"}, headers=auth(admin))
    assert added.status_code == 201
    assert added.json()["status"] == "active"

    members = client.get(f"/v1/organizations/{org_id}/members", headers=auth(admin)).json()
    assert len(members) == 2

    again = client.post(f"/v1/organizations/{org_id}/members",
                        json={"email": "admin2@test.io"}, headers=auth(admin))
    assert again.status_code == 409

    removed = client.delete(f"/v1/organizations/{org_id}/members/{second['user']['id']}",
                            headers=auth(admin))
    assert removed.status_code == 204
    members = client.get(f"/v1/organizations/{org_id}/members", headers=auth(admin)).json()
    assert len(members) == 1


def test_suspended_membership_grants_nothing(client, register, analyze, make_admin, auth, db):
    admin = make_admin()
    owner = register("owner@test.io")
    org_id = admin["user"]["organizations"][0]["id"]
    case_id = analyze(owner, "i will kill you")["caseId"]
    client.post(f"/v1/cases/{case_id}/shares", json={"organizationId": org_id},
                headers=auth(owner))
    assert client.get(f"/v1/cases/{case_id}", headers=auth(admin)).status_code == 200

    with db() as conn:
        conn.execute("UPDATE organization_memberships SET status = 'suspended'"
                     " WHERE user_id = ?", (admin["user"]["id"],))
        conn.commit()

    # The membership status is a control, not a label: it revokes case access
    # and member management alike.
    assert client.get(f"/v1/cases/{case_id}", headers=auth(admin)).status_code == 404
    assert client.get(f"/v1/organizations/{org_id}/members",
                      headers=auth(admin)).status_code == 403


def test_only_admin_accounts_can_join_organizations(client, register, make_admin, auth):
    admin = make_admin()
    register("regular@test.io")
    org_id = admin["user"]["organizations"][0]["id"]

    rejected = client.post(f"/v1/organizations/{org_id}/members",
                           json={"email": "regular@test.io"}, headers=auth(admin))
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "not_admin_account"

    unknown = client.post(f"/v1/organizations/{org_id}/members",
                          json={"email": "ghost@test.io"}, headers=auth(admin))
    assert unknown.status_code == 404


def test_owner_requests_review_and_a_review_clears_it(client, register, analyze, auth):
    owner = register("owner@test.io")
    case_id = analyze(owner, "you are an idiot")["caseId"]

    patched = client.patch(f"/v1/cases/{case_id}", json={"requestReview": True},
                           headers=auth(owner))
    assert patched.status_code == 200
    assert patched.json()["reviewRequested"] is True

    client.post(f"/v1/cases/{case_id}/reviews", json={"note": "Looked at this together."},
                headers=auth(owner))
    detail = client.get(f"/v1/cases/{case_id}", headers=auth(owner)).json()
    assert detail["reviewRequested"] is False
    assert detail["status"] == "reviewed"
