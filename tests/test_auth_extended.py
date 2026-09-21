"""Extended auth, sessions, and admin RBAC tests."""

from tests.conftest import auth


# ---- helpers ---------------------------------------------------------------

def _fresh_login(client, email="demo@nexus.io", password="demo1234"):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


# ---- session revocation ----------------------------------------------------

def test_logout_revokes_session(client):
    token = _fresh_login(client)
    me1 = client.get("/api/auth/me", headers=auth(token))
    assert me1.status_code == 200
    res = client.post("/api/auth/logout", headers=auth(token))
    assert res.status_code == 200
    me2 = client.get("/api/auth/me", headers=auth(token))
    assert me2.status_code == 401


def test_admin_rejected_without_admin_role(client, viewer_token):
    res = client.get("/api/admin/dashboard", headers=auth(viewer_token))
    assert res.status_code == 403


def test_admin_dashboard_requires_token(client):
    assert client.get("/api/admin/dashboard").status_code == 401


# ---- admin (fresh login per test) ------------------------------------------

def test_admin_users_list(client):
    token = _fresh_login(client)
    res = client.get("/api/admin/users", headers=auth(token))
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 4
    emails = [u["email"] for u in data["users"]]
    assert "manager@nexus.io" in emails


def test_admin_update_role(client):
    token = _fresh_login(client)
    users = client.get("/api/admin/users", headers=auth(token)).json()["users"]
    target = next((u for u in users if u["role"] == "VIEWER"), None)
    if not target:
        target = users[0]
    res = client.put(
        f"/api/admin/users/{target['id']}/role",
        json={"role": "ANALYST"},
        headers=auth(token),
    )
    assert res.status_code == 200
    client.put(f"/api/admin/users/{target['id']}/role", json={"role": "VIEWER"}, headers=auth(token))


def test_admin_agent_config(client):
    token = _fresh_login(client)
    agents = client.get("/api/admin/agents", headers=auth(token)).json()["agents"]
    assert len(agents) >= 10
    key = agents[0]["key"]
    up = client.put(
        f"/api/admin/agents/{key}",
        json={"provider": "gemini", "model": "gemini-2.0-flash"},
        headers=auth(token),
    )
    assert up.status_code == 200
    client.put(f"/api/admin/agents/{key}", json={"provider": "", "model": ""}, headers=auth(token))


def test_admin_audit_log(client):
    token = _fresh_login(client)
    res = client.get("/api/admin/audit", headers=auth(token))
    assert res.status_code == 200
    assert "logs" in res.json()


def test_admin_providers(client):
    token = _fresh_login(client)
    res = client.get("/api/admin/providers", headers=auth(token))
    assert res.status_code == 200
    providers = res.json()["providers"]
    names = [p["provider"] for p in providers]
    assert "openai" in names


def test_agents_endpoint_includes_provider_fields(client, viewer_token):
    res = client.get("/api/agents", headers=auth(viewer_token))
    assert res.status_code == 200
    a = res.json()["agents"][0]
    assert "provider" in a
    assert "model" in a