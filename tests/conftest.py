"""Shared test configuration: SQLite-backed app + authenticated client."""

import os
import sys
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(
    tempfile.gettempdir(), "nexus_test.db"
).replace("\\", "/")
os.environ["DEMO_MODE"] = "true"
os.environ["DEBUG"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    # Rebuild the schema so new columns/tables are always present.
    from app.database.session import Base, engine

    engine.dispose()
    with engine.begin() as conn:
        Base.metadata.drop_all(conn)
        Base.metadata.create_all(conn)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_token(client):
    return _login(client, "demo@nexus.io", "demo1234")


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Reset the in-memory rate limiter between tests so auth throttling
    never makes the suite order-dependent."""
    from app.services.limiter import _limiter

    yield
    _limiter.clear()


@pytest.fixture(scope="session")
def manager_token(client):
    return _login(client, "manager@nexus.io", "manager123")


@pytest.fixture(scope="session")
def viewer_token(client):
    return _login(client, "viewer@nexus.io", "viewer123")


def _login(client, email, password):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}