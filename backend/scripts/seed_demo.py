"""Seed synthetic demonstration accounts and content (roadmap week 1–2).

Everything here is fictional and safe to show in a demo:

    conda activate a-mbl
    python -m backend.scripts.seed_demo

Accounts (password for all: demo-pass-123):
    demo.user@a-mbl.test       adult User with sample cases
    demo.guardian@a-mbl.test   Guardian (linked to the teen account)
    demo.teen@a-mbl.test       13-17 User, activated by the guardian link
    demo.admin@a-mbl.test      School Administrator for "Demo High School"
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import create_app  # noqa: E402
from backend.scripts.create_admin import create_admin  # noqa: E402

PASSWORD = "demo-pass-123"

SAMPLES = [
    # Together these cover every case severity: caution, high, and critical.
    ("Had a great day at school today, see you tomorrow!", "text", None, None),
    ("that new rule is so stupid, this app is trash", "text", "ChatApp", None),
    ("you are such an idiot and a loser, everyone hates you", "text", "ChatApp", "anon_17"),
    ("stop showing up or i will hurt you, you're dead tomorrow", "text", "ChatApp", "anon_17"),
    ("nobody likes you, just stop coming to school", "screenshot", "PicShare", None),
]


def seed() -> None:
    app = create_app()
    with TestClient(app) as client:
        def register(email, name, role, year, month):
            response = client.post("/v1/auth/register", json={
                "email": email, "password": PASSWORD, "displayName": name,
                "role": role, "birthYear": year, "birthMonth": month,
            })
            if response.status_code == 409:
                response = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
            response.raise_for_status()
            return response.json()

        def bearer(session):
            return {"Authorization": f"Bearer {session['accessToken']}"}

        def has_cases(session):
            return client.get("/v1/cases", headers=bearer(session)).json().get("total", 0) > 0

        user = register("demo.user@a-mbl.test", "Demo User", "user", 2000, 5)
        guardian = register("demo.guardian@a-mbl.test", "Demo Guardian", "guardian", 1985, 3)
        # Relative to today so the teen stays 13-17 whenever the seed runs.
        teen = register("demo.teen@a-mbl.test", "Demo Teen", "user", date.today().year - 15, 1)

        if teen.get("linkCode"):
            client.post("/v1/guardian-links/accept",
                        json={"code": teen["linkCode"]}, headers=bearer(guardian))

        # Re-running the seed must not pile up duplicate sample cases.
        if not has_cases(user):
            for text, source, platform, alias in SAMPLES:
                client.post("/v1/analyses", json={
                    "text": text, "sourceType": source,
                    "platformName": platform, "senderAlias": alias,
                }, headers=bearer(user))

        # A harmful message submitted by the linked teen alerts the guardian.
        if not has_cases(teen):
            client.post("/v1/analyses", json={
                "text": "watch your back after class, you will regret this",
                "sourceType": "text",
            }, headers=bearer(teen))

    try:
        create_admin("Demo High School", "demo.admin@a-mbl.test", PASSWORD, "Demo Admin")
    except SystemExit as exc:
        print(exc)

    print("Demo data ready. Password for all accounts: " + PASSWORD)


if __name__ == "__main__":
    seed()
