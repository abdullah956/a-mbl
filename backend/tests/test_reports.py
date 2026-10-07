"""Role-scoped summaries and masked PDF generation."""


def test_summary_counts_by_label_and_severity(client, register, analyze, auth):
    session = register("report@test.io")
    analyze(session, "you are an idiot")
    analyze(session, "i will kill you")
    analyze(session, "nobody likes you, loser")
    analyze(session, "totally fine message")  # no case

    summary = client.get("/v1/reports/summary", headers=auth(session)).json()
    assert summary["total"] == 3
    assert summary["byLabel"] == {"offensive": 1, "threat": 1, "harassment": 1}
    assert summary["bySeverity"] == {"caution": 1, "critical": 1, "high": 1}
    assert summary["pending"] == 3
    assert summary["weekly"] and sum(w["count"] for w in summary["weekly"]) == 3


def test_summary_top_senders_and_weekday(client, register, analyze, auth):
    session = register("senders@test.io")
    analyze(session, "i will kill you", senderAlias="bully01", platformName="Instagram")
    analyze(session, "nobody likes you, loser", senderAlias="bully01")
    analyze(session, "you are an idiot", senderAlias="someone else")
    analyze(session, "i will kill you")  # no alias -> not counted as a sender

    summary = client.get("/v1/reports/summary", headers=auth(session)).json()
    assert summary["topSenders"] == [
        {"alias": "bully01", "count": 2},
        {"alias": "someone else", "count": 1},
    ]
    assert len(summary["byWeekday"]) == 7
    assert sum(summary["byWeekday"]) == 4


def test_summary_respects_role_scope(client, make_linked_pair, register, analyze, auth):
    teen, guardian = make_linked_pair()
    stranger = register("stranger@test.io")
    analyze(teen, "i will kill you")
    analyze(stranger, "i will kill you")

    guardian_summary = client.get("/v1/reports/summary", headers=auth(guardian)).json()
    assert guardian_summary["total"] == 1  # linked teen only, never the stranger

    stranger_summary = client.get("/v1/reports/summary", headers=auth(stranger)).json()
    assert stranger_summary["total"] == 1


def test_invalid_date_range_rejected(client, register, auth):
    session = register("dates@test.io")
    bad = client.get("/v1/reports/summary?rangeFrom=july-first", headers=auth(session))
    assert bad.status_code == 422
    swapped = client.get("/v1/reports/summary?rangeFrom=2026-07-10&rangeTo=2026-07-01",
                         headers=auth(session))
    assert swapped.status_code == 422


def _spy_on_pdf(monkeypatch):
    """Capture the exact data handed to the PDF builder while still building it."""
    from backend.app import pdf as pdf_module

    captured = {}
    real = pdf_module.build_report

    def spy(**kwargs):
        captured.clear()
        captured.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr("backend.app.pdf.build_report", spy)
    return captured


def test_pdf_is_generated_and_masked(client, register, analyze, auth, monkeypatch):
    captured = _spy_on_pdf(monkeypatch)
    session = register("pdf@test.io")
    analyze(session, "i will kill you tomorrow")

    response = client.post("/v1/reports/pdf", json={}, headers=auth(session))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 1000

    # Exactly one case went into the PDF, and its preview masks the raw phrase.
    assert len(captured["cases"]) == 1
    assert "kill you" not in captured["cases"][0]["maskedPreview"]
    assert captured["summary"]["total"] == 1


def test_summary_groups_by_sender_alias_only_when_given(client, register, analyze, auth):
    session = register("alias@test.io")
    analyze(session, "you are an idiot", senderAlias="anon_17")
    analyze(session, "nobody likes you, loser", senderAlias="anon_17")
    analyze(session, "i will kill you")  # no alias -> not grouped

    summary = client.get("/v1/reports/summary", headers=auth(session)).json()
    assert summary["bySender"] == {"anon_17": 2}
    assert summary["total"] == 3


def test_pdf_includes_review_notes_for_cases_in_scope(client, register, analyze, auth,
                                                      monkeypatch):
    captured = _spy_on_pdf(monkeypatch)
    session = register("notes@test.io")
    case_id = analyze(session, "i will kill you tomorrow")["caseId"]
    client.post(f"/v1/cases/{case_id}/reviews",
                json={"humanLabel": "threat", "note": "Verified with <b>screenshots & context"},
                headers=auth(session))

    response = client.post("/v1/reports/pdf", json={}, headers=auth(session))
    assert response.status_code == 200
    reviews = captured["cases"][0]["reviews"]
    assert reviews[0]["humanLabel"] == "threat"
    assert reviews[0]["note"].startswith("Verified with <b>")  # markup survives escaping


def test_pdf_survives_many_long_review_notes(client, register, analyze, auth):
    # Long, numerous review notes must be capped so the table row still fits an
    # A4 frame — otherwise ReportLab raises LayoutError and the report 500s.
    session = register("longnotes@test.io")
    case_id = analyze(session, "i will kill you tomorrow")["caseId"]
    for i in range(8):
        client.post(f"/v1/cases/{case_id}/reviews",
                    json={"humanLabel": "threat", "note": f"Note {i} " + "x" * 2000},
                    headers=auth(session))

    response = client.post("/v1/reports/pdf", json={}, headers=auth(session))
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_pdf_survives_markup_in_names_and_case_text(client, register, analyze, auth):
    # ReportLab's Paragraph parses mini-XML; unescaped '<b>' or '&' in the
    # display name or masked preview used to crash the whole report with a 500.
    session = register("markup@test.io", name="<b>Mark & Up")
    analyze(session, "you are an <b>idiot & a <loser")

    response = client.post("/v1/reports/pdf", json={}, headers=auth(session))
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_pdf_respects_role_scope(client, make_linked_pair, register, analyze, auth,
                                 monkeypatch):
    captured = _spy_on_pdf(monkeypatch)
    teen, guardian = make_linked_pair()
    stranger = register("stranger@test.io")
    analyze(teen, "i will kill you tomorrow")

    guardian_pdf = client.post("/v1/reports/pdf", json={}, headers=auth(guardian))
    assert guardian_pdf.status_code == 200
    assert len(captured["cases"]) == 1  # the linked teen's case is in scope

    stranger_pdf = client.post("/v1/reports/pdf", json={}, headers=auth(stranger))
    assert stranger_pdf.status_code == 200
    assert captured["cases"] == []      # nothing leaks outside the role scope
