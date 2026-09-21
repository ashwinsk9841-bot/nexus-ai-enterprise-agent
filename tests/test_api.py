"""API endpoint tests: dashboard, security, operations, incidents, reports."""

from datetime import datetime

from tests.conftest import auth


def test_dashboard_overview(client, admin_token):
    res = client.get("/api/dashboard/overview", headers=auth(admin_token))
    assert res.status_code == 200
    body = res.json()
    assert "health" in body and "business" in body and "operations" in body
    assert body["health"]["db_health"] in ("HEALTHY", "DEGRADED")
    assert "revenue" in body["trends"]


def test_analytics_metrics(client, admin_token):
    res = client.get("/api/analytics/metrics?days=7", headers=auth(admin_token))
    assert res.status_code == 200
    body = res.json()
    assert "revenue" in body["metrics"]
    assert len(body["metrics"]["revenue"]["values"]) > 0


def test_analytics_export_csv(client, admin_token):
    res = client.post(
        "/api/analytics/export", json={"days": 7}, headers=auth(admin_token)
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "nexus-analytics.csv" in res.headers.get("content-disposition", "")


def test_analytics_explain(client, admin_token):
    res = client.post(
        "/api/analytics/explain", json={"days": 30}, headers=auth(admin_token)
    )
    assert res.status_code == 200
    assert "explanation" in res.json()


def test_security_summary(client, admin_token):
    res = client.get("/api/security/summary", headers=auth(admin_token))
    assert res.status_code == 200
    summary = res.json()["summary"]
    assert 0 <= summary["security_score"] <= 100
    assert summary["risk_level"] in ("NORMAL", "ELEVATED", "HIGH")
    assert set(summary["by_severity"]) == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def test_security_events(client, admin_token):
    res = client.get("/api/security/events?limit=10", headers=auth(admin_token))
    assert res.status_code == 200
    assert len(res.json()["events"]) <= 10


def test_operations_metrics(client, admin_token):
    res = client.get(
        "/api/operations/metrics?service=api&minutes=60", headers=auth(admin_token)
    )
    assert res.status_code == 200
    body = res.json()
    assert "cpu_usage" in body["metrics"]
    assert body["latest"]["db_health"] in ("HEALTHY", "DEGRADED")


def test_incident_lifecycle(client, admin_token):
    headers = auth(admin_token)
    created = client.post(
        "/api/incidents",
        json={
            "title": "Test incident",
            "description": "Created by pytest",
            "severity": "HIGH",
            "status": "Detected",
            "assigned_agent": "devops",
        },
        headers=headers,
    )
    assert created.status_code == 200
    inc_id = created.json()["id"]
    assert created.json()["incident_id"].startswith("INC-")

    listed = client.get("/api/incidents", headers=headers).json()["incidents"]
    assert any(i["id"] == inc_id for i in listed)

    updated = client.patch(
        f"/api/incidents/{inc_id}",
        json={"status": "Investigating", "title": "Test incident", "description": "x"},
        headers=headers,
    )
    assert updated.status_code == 200

    detail = client.get(f"/api/incidents/{inc_id}", headers=headers)
    assert detail.status_code == 200
    events = detail.json()["events"]
    assert any(e["event_type"] == "status" for e in events)


def test_notifications(client, admin_token):
    res = client.get("/api/notifications", headers=auth(admin_token))
    assert res.status_code == 200
    notifs = res.json()["notifications"]
    if notifs:
        nid = notifs[0]["id"]
        read = client.post(f"/api/notifications/{nid}/read", headers=auth(admin_token))
        assert read.status_code == 200
        assert read.json()["read"] is True


def test_reports_generate(client, admin_token):
    res = client.post(
        "/api/reports/generate",
        json={"report_type": "daily", "date_range": 7},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    report = res.json()["report"]
    assert report["report_type"] == "daily"
    assert "Executive" in report["title"]


def test_ai_command_requires_query(client, admin_token):
    res = client.post("/api/ai/command", json={"query": "   "}, headers=auth(admin_token))
    assert res.status_code == 400