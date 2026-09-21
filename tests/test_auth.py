"""Authentication & RBAC tests."""

from tests.conftest import auth


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["demo_mode"] is True


def test_login_success(client):
    res = client.post("/api/auth/login", json={"email": "demo@nexus.io", "password": "demo1234"})
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "ADMIN"


def test_login_wrong_password(client):
    res = client.post("/api/auth/login", json={"email": "demo@nexus.io", "password": "nope"})
    assert res.status_code == 401


def test_login_unknown_user(client):
    res = client.post("/api/auth/login", json={"email": "ghost@nexus.io", "password": "x"})
    assert res.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_token(client, admin_token):
    res = client.get("/api/auth/me", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["role"] == "ADMIN"


def test_invalid_token_rejected(client):
    res = client.get("/api/auth/me", headers=auth("not-a-valid-jwt"))
    assert res.status_code == 401


def test_role_gate_blocks_viewer(client, viewer_token):
    good = client.get("/api/dashboard/overview", headers=auth(viewer_token))
    assert good.status_code == 200
    bad = client.post(
        "/api/approvals/1/decide",
        json={"decision": "APPROVED"},
        headers=auth(viewer_token),
    )
    assert bad.status_code == 403