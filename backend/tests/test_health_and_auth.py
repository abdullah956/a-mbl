"""Health, registration/age gate, login, token rotation, and profile."""

from datetime import date

from .conftest import PASSWORD


def test_health_reports_model_and_ocr(client):
    body = client.get("/v1/health").json()
    assert body["status"] == "ok"
    assert body["modelReady"] is True
    assert body["modelVersion"].startswith("lexicon-")
    assert isinstance(body["ocrReady"], bool)


def test_adult_user_registers_active(register):
    session = register("adult@test.io")
    assert session["user"]["status"] == "active"
    assert session["user"]["ageBand"] == "18+"
    assert session["linkCode"] is None
    assert session["accessToken"] and session["refreshToken"]


def test_teen_registers_pending_with_link_code(register_teen):
    session = register_teen()
    assert session["user"]["status"] == "pending_guardian"
    assert session["user"]["ageBand"] == "13-17"
    assert len(session["linkCode"]) == 8


def test_under_13_is_refused_and_no_account_exists(client, db):
    response = client.post("/v1/auth/register", json={
        "email": "kid@test.io", "password": PASSWORD, "displayName": "Kid",
        "role": "user", "birthYear": date.today().year - 10, "birthMonth": 1,
    })
    assert response.status_code == 403
    assert response.json()["code"] == "age_not_supported"
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0


def test_guardian_must_be_adult(client):
    response = client.post("/v1/auth/register", json={
        "email": "youngguardian@test.io", "password": PASSWORD, "displayName": "G",
        "role": "guardian", "birthYear": date.today().year - 15, "birthMonth": 1,
    })
    assert response.status_code == 403
    assert response.json()["code"] == "guardian_must_be_adult"


def test_school_admin_is_not_a_public_role(client):
    response = client.post("/v1/auth/register", json={
        "email": "sneaky@test.io", "password": PASSWORD, "displayName": "S",
        "role": "school_admin", "birthYear": 1990, "birthMonth": 1,
    })
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_duplicate_email_conflicts(register):
    register("dup@test.io")
    register("dup@test.io", expect=409)


def test_short_password_and_bad_email_are_field_errors(client):
    response = client.post("/v1/auth/register", json={
        "email": "not-an-email", "password": "short", "displayName": "X",
        "role": "user", "birthYear": 1990, "birthMonth": 1,
    })
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert "email" in body["fieldErrors"] and "password" in body["fieldErrors"]
    assert body["requestId"]


def test_login_and_wrong_password(client, register):
    register("login@test.io")
    ok = client.post("/v1/auth/login", json={"email": "login@test.io", "password": PASSWORD})
    assert ok.status_code == 200
    bad = client.post("/v1/auth/login", json={"email": "login@test.io", "password": "wrong-pass"})
    assert bad.status_code == 401
    assert bad.json()["code"] == "invalid_credentials"


def test_login_rate_limited(client, register):
    register("throttle@test.io")
    for _ in range(8):
        client.post("/v1/auth/login", json={"email": "throttle@test.io", "password": "wrong-pass"})
    response = client.post("/v1/auth/login",
                           json={"email": "throttle@test.io", "password": PASSWORD})
    assert response.status_code == 429


def test_refresh_rotation_and_reuse_detection(client, register):
    session = register("rotate@test.io")
    first = client.post("/v1/auth/refresh", json={"refreshToken": session["refreshToken"]})
    assert first.status_code == 200
    rotated = first.json()

    # Re-using the rotated-out token fails and revokes the whole chain.
    reuse = client.post("/v1/auth/refresh", json={"refreshToken": session["refreshToken"]})
    assert reuse.status_code == 401
    after = client.post("/v1/auth/refresh", json={"refreshToken": rotated["refreshToken"]})
    assert after.status_code == 401


def test_logout_revokes_refresh_token(client, register, auth):
    session = register("logout@test.io")
    response = client.post("/v1/auth/logout", json={"refreshToken": session["refreshToken"]},
                           headers=auth(session))
    assert response.status_code == 204
    refresh = client.post("/v1/auth/refresh", json={"refreshToken": session["refreshToken"]})
    assert refresh.status_code == 401


def test_logout_works_without_access_token(client, register):
    # Sign-out must succeed even after the 15-minute access token expires:
    # possession of the refresh token is the credential.
    session = register("logout2@test.io")
    response = client.post("/v1/auth/logout", json={"refreshToken": session["refreshToken"]})
    assert response.status_code == 204
    refresh = client.post("/v1/auth/refresh", json={"refreshToken": session["refreshToken"]})
    assert refresh.status_code == 401


def test_tampered_access_tokens_rejected(client, register):
    import base64
    import json as jsonlib

    session = register("tamper@test.io")
    body, sig = session["accessToken"].split(".")

    flipped_sig = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    assert client.get("/v1/me", headers={
        "Authorization": f"Bearer {body}.{flipped_sig}"}).status_code == 401

    forged = jsonlib.dumps({"uid": "someone-else", "exp": "2999-01-01T00:00:00+00:00"})
    forged_body = base64.urlsafe_b64encode(forged.encode()).rstrip(b"=").decode()
    assert client.get("/v1/me", headers={
        "Authorization": f"Bearer {forged_body}.{sig}"}).status_code == 401

    assert client.get("/v1/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_expired_refresh_token_rejected(client, register, db):
    session = register("expired@test.io")
    with db() as conn:
        conn.execute("UPDATE refresh_tokens SET expires_at = '2020-01-01T00:00:00+00:00'")
        conn.commit()
    response = client.post("/v1/auth/refresh", json={"refreshToken": session["refreshToken"]})
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_refresh"


def test_me_requires_token_and_can_update_name(client, register, auth):
    assert client.get("/v1/me").status_code == 401
    session = register("me@test.io")
    assert client.get("/v1/me", headers=auth(session)).json()["email"] == "me@test.io"
    updated = client.patch("/v1/me", json={"displayName": "New Name"}, headers=auth(session))
    assert updated.json()["displayName"] == "New Name"


def test_malformed_json_body_returns_400(client, register, auth):
    session = register("json@test.io")
    response = client.post("/v1/analyses", content=b"{not valid json",
                           headers={**auth(session), "Content-Type": "application/json"})
    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"
