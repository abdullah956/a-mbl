"""Shared fixtures: every test gets a fresh temporary data directory (SQLite
database, key files, evidence folder) and a fresh app instance."""

import io
import sys
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASSWORD = "password-123"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("A_MBL_DATA_DIR", str(tmp_path / "data"))
    from fastapi.testclient import TestClient

    from backend.app import rate_limit
    from backend.app.main import create_app

    rate_limit.reset()
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def db():
    """Open a direct connection to the test database (caller closes it)."""
    from backend.app.db import connect

    def _open():
        return closing(connect())

    return _open


@pytest.fixture()
def register(client):
    def _register(email, role="user", year=1995, month=6, name=None, expect=201):
        response = client.post("/v1/auth/register", json={
            "email": email,
            "password": PASSWORD,
            "displayName": name or email.split("@")[0],
            "role": role,
            "birthYear": year,
            "birthMonth": month,
        })
        assert response.status_code == expect, response.text
        return response.json()

    return _register


@pytest.fixture()
def register_teen(register):
    def _register_teen(email="teen@test.io"):
        return register(email, year=date.today().year - 15, month=1)

    return _register_teen


@pytest.fixture()
def make_admin(client):
    def _make_admin(org="Test School", email="admin@test.io", name="Test Admin"):
        from backend.scripts.create_admin import create_admin

        create_admin(org, email, PASSWORD, name)
        response = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return response.json()

    return _make_admin


@pytest.fixture()
def auth():
    def _auth(session):
        return {"Authorization": f"Bearer {session['accessToken']}"}

    return _auth


@pytest.fixture()
def analyze(client, auth):
    def _analyze(session, text, expect=201, **extra):
        response = client.post("/v1/analyses", json={"text": text, **extra},
                               headers=auth(session))
        assert response.status_code == expect, response.text
        return response.json()

    return _analyze


@pytest.fixture()
def png_bytes():
    from PIL import Image

    def _png(size=(64, 64)):
        buffer = io.BytesIO()
        Image.new("RGB", size, (200, 180, 220)).save(buffer, format="PNG")
        return buffer.getvalue()

    return _png


def linked_pair(register, register_teen, client, auth):
    """Create a guardian linked to an activated teen. Returns (teen, guardian)."""
    teen = register_teen()
    guardian = register("guardian@test.io", role="guardian", year=1980)
    response = client.post("/v1/guardian-links/accept",
                           json={"code": teen["linkCode"]}, headers=auth(guardian))
    assert response.status_code == 201, response.text
    return teen, guardian


@pytest.fixture()
def make_linked_pair(register, register_teen, client, auth):
    return lambda: linked_pair(register, register_teen, client, auth)
