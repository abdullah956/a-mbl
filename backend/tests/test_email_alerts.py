"""Email alerts mirror in-app alerts when SMTP is configured (FR5).

The suite never opens a real SMTP connection: delivery is captured at the
_send_one seam, and _spawn is made synchronous so assertions see the result.
"""

from backend.app import emailer


def _configure(monkeypatch, sent):
    monkeypatch.setenv("A_MBL_SMTP_HOST", "smtp.test.local")
    monkeypatch.setenv("A_MBL_SMTP_FROM", "alerts@a-mbl.test")
    monkeypatch.setattr(emailer, "_spawn", lambda *args: emailer._deliver(*args))
    monkeypatch.setattr(emailer, "_send_one", lambda config, message: sent.append(message))


def test_unconfigured_by_default():
    assert emailer.available() is False


def test_guardian_gets_email_without_content(client, make_linked_pair, analyze, auth, monkeypatch):
    sent = []
    _configure(monkeypatch, sent)

    teen, guardian = make_linked_pair()
    analyze(teen, "i will kill you")

    # The guardian is emailed; the owner never is (they just saw the result).
    assert [m["To"] for m in sent] == ["guardian@test.io"]
    message = sent[0]
    assert "critical" in message["Subject"]
    body = message.get_content().lower()
    assert "kill" not in body  # never any message content
    assert "critical" in body and "threat" in body


def test_repeated_share_does_not_resend(client, register, make_admin, analyze, auth, monkeypatch):
    sent = []
    _configure(monkeypatch, sent)

    make_admin()
    session = register("victim@test.io")
    case_id = analyze(session, "i will kill you")["caseId"]
    org_id = client.get("/v1/organizations", headers=auth(session)).json()[0]["id"]

    for _ in range(2):
        response = client.post(f"/v1/cases/{case_id}/shares",
                               json={"organizationId": org_id}, headers=auth(session))
        assert response.status_code in (201, 409), response.text

    admin_emails = [m for m in sent if m["To"] == "admin@test.io"]
    assert len(admin_emails) == 1  # alert row dedup also dedupes email
