"""Guardian link codes, approval, activation, and revocation (roadmap §7.1)."""

from .conftest import PASSWORD


def test_guardian_approval_activates_teen(client, register, register_teen, auth):
    teen = register_teen()
    guardian = register("guardian@test.io", role="guardian", year=1980)

    accepted = client.post("/v1/guardian-links/accept",
                           json={"code": teen["linkCode"]}, headers=auth(guardian))
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["status"] == "active"

    me = client.get("/v1/me", headers=auth(teen)).json()
    assert me["status"] == "active", me


def test_code_is_single_use(client, register, register_teen, auth):
    teen = register_teen()
    guardian_a = register("g1@test.io", role="guardian", year=1980)
    guardian_b = register("g2@test.io", role="guardian", year=1981)

    first = client.post("/v1/guardian-links/accept",
                        json={"code": teen["linkCode"]}, headers=auth(guardian_a))
    assert first.status_code == 201
    second = client.post("/v1/guardian-links/accept",
                         json={"code": teen["linkCode"]}, headers=auth(guardian_b))
    assert second.status_code == 404
    assert second.json()["code"] == "code_invalid"


def test_expired_code_is_rejected(client, register, register_teen, auth, db):
    teen = register_teen()
    guardian = register("g@test.io", role="guardian", year=1980)
    with db() as conn:
        conn.execute("UPDATE guardian_link_codes SET expires_at = '2020-01-01T00:00:00+00:00'")
        conn.commit()
    response = client.post("/v1/guardian-links/accept",
                           json={"code": teen["linkCode"]}, headers=auth(guardian))
    assert response.status_code == 404


def test_only_guardian_accounts_accept_codes(client, register, register_teen, auth):
    teen = register_teen()
    other_user = register("user2@test.io")
    response = client.post("/v1/guardian-links/accept",
                           json={"code": teen["linkCode"]}, headers=auth(other_user))
    assert response.status_code == 403


def test_pending_teen_can_create_new_code(client, register_teen, auth):
    teen = register_teen()
    response = client.post("/v1/guardian-links", headers=auth(teen))
    assert response.status_code == 201
    assert len(response.json()["code"]) == 8


def test_guardians_cannot_create_codes(client, register, auth):
    guardian = register("g@test.io", role="guardian", year=1980)
    assert client.post("/v1/guardian-links", headers=auth(guardian)).status_code == 403


def test_either_side_can_revoke(client, make_linked_pair, auth):
    teen, guardian = make_linked_pair()
    links = client.get("/v1/guardian-links", headers=auth(teen)).json()
    assert len(links) == 1

    revoked = client.delete(f"/v1/guardian-links/{links[0]['id']}", headers=auth(guardian))
    assert revoked.status_code == 204
    assert client.get("/v1/guardian-links", headers=auth(teen)).json()[0]["status"] == "revoked"

    # The teen account stays active after revocation.
    assert client.get("/v1/me", headers=auth(teen)).json()["status"] == "active"


def test_guardian_previews_code_before_approving(client, register, register_teen, auth):
    teen = register_teen()
    guardian = register("guardian@test.io", role="guardian", year=1980)

    preview = client.post("/v1/guardian-links/preview", json={"code": teen["linkCode"]},
                          headers=auth(guardian))
    assert preview.status_code == 200
    assert preview.json()["userName"] == "teen"
    assert preview.json()["userAgeBand"] == "13-17"

    # The preview must not consume the code: approval still works afterwards.
    accepted = client.post("/v1/guardian-links/accept", json={"code": teen["linkCode"]},
                           headers=auth(guardian))
    assert accepted.status_code == 201


def test_preview_rejects_bad_codes_and_non_guardians(client, register, register_teen, auth):
    teen = register_teen()
    guardian = register("guardian@test.io", role="guardian", year=1980)
    user = register("someone@test.io")

    wrong = client.post("/v1/guardian-links/preview", json={"code": "WRONGCODE"},
                        headers=auth(guardian))
    assert wrong.status_code == 404

    denied = client.post("/v1/guardian-links/preview", json={"code": teen["linkCode"]},
                         headers=auth(user))
    assert denied.status_code == 403


def test_link_grants_no_access_to_unrelated_users(client, make_linked_pair, register, analyze, auth):
    teen, guardian = make_linked_pair()
    stranger = register("stranger@test.io")
    result = analyze(stranger, "watch your back tomorrow")
    assert result["caseId"]

    response = client.get(f"/v1/cases/{result['caseId']}", headers=auth(guardian))
    assert response.status_code == 404
