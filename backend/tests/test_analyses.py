"""Text analysis flow: results, retention rules, and raw-text privacy."""

from backend.app import config


def test_normal_text_returns_result_and_stores_no_case(client, register, analyze, db):
    session = register("normal@test.io")
    result = analyze(session, "See you at practice tomorrow!")
    assert result["primaryLabel"] == "normal"
    assert result["severity"] == "safe"
    assert result["caseId"] is None
    assert result["retainedUntil"] is None
    assert result["advice"]
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM flagged_cases").fetchone()["n"] == 0


def test_normal_raw_text_is_not_retained_anywhere(client, register, analyze, tmp_path):
    session = register("privacy@test.io")
    marker = "zebraQuietMarkerXyz"
    analyze(session, f"Nice weather today {marker} let's play outside")

    db_file = config.db_path()
    assert marker.encode() not in db_file.read_bytes()
    assert not any((config.data_dir() / "evidence").iterdir())


def test_harmful_text_is_stored_encrypted_only(client, register, analyze, auth):
    session = register("case@test.io")
    marker = "zebraSecretLocationAbc"
    result = analyze(session, f"i will kill you, meet me at {marker}")
    assert result["primaryLabel"] == "threat"
    assert result["severity"] == "critical"
    assert result["caseId"]
    assert result["retainedUntil"]

    # The database file never contains the plaintext.
    assert marker.encode() not in config.db_path().read_bytes()

    # But the owner can still read the decrypted text through the API,
    # while the preview masks the matched harmful phrase.
    detail = client.get(f"/v1/cases/{result['caseId']}", headers=auth(session)).json()
    assert marker in detail["text"]
    assert "kill" not in detail["maskedPreview"]


def test_offensive_creates_case_with_thirty_day_expiry(register, analyze):
    session = register("offense@test.io")
    result = analyze(session, "you are an idiot")
    assert result["primaryLabel"] == "offensive"
    assert result["severity"] == "caution"
    assert result["caseId"] is not None
    assert result["retainedUntil"] is not None


def test_uncertain_result_sets_needs_review(register, analyze):
    session = register("uncertain@test.io")
    result = analyze(session, "idiot")
    assert result["needsReview"] is True
    assert any("uncertain" in line.lower() for line in result["advice"])


def test_empty_and_oversized_text_are_rejected(client, register, auth):
    session = register("bounds@test.io")
    empty = client.post("/v1/analyses", json={"text": "   "}, headers=auth(session))
    assert empty.status_code == 422
    huge = client.post("/v1/analyses", json={"text": "a" * 5001}, headers=auth(session))
    assert huge.status_code == 422


def test_pending_teen_cannot_analyze(client, register_teen, auth):
    teen = register_teen()
    response = client.post("/v1/analyses", json={"text": "hello"}, headers=auth(teen))
    assert response.status_code == 403
    assert response.json()["code"] == "account_pending"


def test_analysis_requires_auth(client):
    assert client.post("/v1/analyses", json={"text": "hello"}).status_code == 401


def test_get_analysis_is_scoped(client, register, analyze, auth):
    owner = register("owner@test.io")
    stranger = register("stranger@test.io")
    result = analyze(owner, "watch your back tomorrow")

    own = client.get(f"/v1/analyses/{result['id']}", headers=auth(owner))
    assert own.status_code == 200
    other = client.get(f"/v1/analyses/{result['id']}", headers=auth(stranger))
    assert other.status_code == 404


def test_guardian_reads_linked_harmful_analysis_but_not_normal(client, make_linked_pair,
                                                               analyze, auth):
    teen, guardian = make_linked_pair()
    harmful = analyze(teen, "i will kill you")
    normal = analyze(teen, "have a lovely day")

    assert client.get(f"/v1/analyses/{harmful['id']}",
                      headers=auth(guardian)).status_code == 200
    # Normal results have no case, so they stay private to their owner.
    assert client.get(f"/v1/analyses/{normal['id']}",
                      headers=auth(guardian)).status_code == 404


def test_safe_result_can_be_flagged_for_review(client, register, auth):
    session = register("flagger@test.io")
    response = client.post("/v1/analyses", json={
        "text": "totally fine message", "flagForReview": True,
    }, headers=auth(session))
    assert response.status_code == 201
    body = response.json()
    assert body["severity"] == "safe"
    assert body["caseId"]  # kept as a case despite the safe result (§6.3)

    case = client.get(f"/v1/cases/{body['caseId']}", headers=auth(session)).json()
    assert case["reviewRequested"] is True
    assert case["text"] == "totally fine message"

    # A Normal message has no flagged terms, so nothing is term-censored — the
    # preview must still hide it rather than pass the raw text through (§15.2).
    assert "totally" not in case["maskedPreview"]
    assert "•" in case["maskedPreview"]

    # Flagged-safe results never alert anyone.
    assert client.get("/v1/alerts", headers=auth(session)).json() == []


def test_flagged_safe_case_is_masked_in_the_pdf(client, register, auth):
    session = register("pdfmask@test.io")
    client.post("/v1/analyses", json={"text": "a private but ordinary note",
                                      "flagForReview": True}, headers=auth(session))

    from backend.app import pdf as pdf_module

    captured = {}
    real = pdf_module.build_report

    def spy(**kwargs):
        captured.update(kwargs)
        return real(**kwargs)

    pdf_module.build_report = spy
    try:
        assert client.post("/v1/reports/pdf", json={}, headers=auth(session)).status_code == 200
    finally:
        pdf_module.build_report = real

    preview = captured["cases"][0]["maskedPreview"]
    assert "private" not in preview and "ordinary" not in preview
