"""Synthetic demo data generator for NEXUS demo mode.

Generates realistic-looking business metrics, system metrics, security
events, incidents, and agent records so the platform is fully functional
without any external enterprise integrations.
"""

import csv
import io
import json
import math
import random
import uuid
from datetime import datetime, timedelta, timezone

from ..models import (
    Agent,
    AgentRun,
    BusinessMetric,
    Incident,
    IncidentEvent,
    Notification,
    SecurityEvent,
    SystemMetric,
)

random.seed(42)

REGIONS = ["North America", "Europe", "APAC", "LATAM", "MEA"]
DEPARTMENTS = ["Sales", "Marketing", "Ops", "Finance", "Support", "IT", "Engineering"]
PRODUCTS = ["Nexus Core", "Nexus Analytics", "Nexus Security", "Nexus Ops", "Nexus AI+"]
SEGMENTS = ["Enterprise", "Mid-Market", "SMB", "Strategic"]

SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
INCIDENT_STATUSES = ["Detected", "Investigating", "Awaiting Approval", "Resolved", "Closed"]

SECURITY_EVENT_TYPES = [
    "Failed login",
    "Suspicious sign-in",
    "Permission change",
    "New device login",
    "API key rotation",
    "Phishing reported",
    "Unusual data export",
    "Malware scan alert",
]


def _utcnow():
    return datetime.now(timezone.utc)


def _random_between(a, b, decimals=2):
    return round(random.uniform(a, b), decimals)


def seed_query_baseline(db, center: float, vol: float, count: int = 120) -> list[dict]:
    """Generate a waxing/waning baseline series for business metrics."""
    rows = []
    today = _utcnow().replace(minute=0, second=0, microsecond=0)
    for i in range(count):
        ts = today - timedelta(days=count - 1 - i)
        wave = 1 + 0.1 * math.sin(i / 12.0) + random.uniform(-vol, vol)
        rows.append({})

    series = []
    series.append(center * (0.9 + 0.2 * random.random()))
    for i in range(1, count):
        prev = series[-1]
        change = random.uniform(-vol, vol) + 0.0
        series.append(max(prev * (1 + change), 1.0))
    return series


def seed_demo_data(db, days: int = 120):
    """Populate the database with synthetic enterprise data."""
    _seed_business_metrics(db, days)
    _seed_system_metrics(db, days)
    _seed_security_events(db, days)
    _seed_incidents(db, days)
    _seed_agents(db)
    _seed_notifications(db)
    _seed_demo_report_if_missing(db)


def _seed_business_metrics(db, days: int):
    if db.query(BusinessMetric).count() > 0:
        return

    today = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    revenue_series = seed_query_baseline(db, 1_250_000, 0.03, days)
    customers_series = seed_query_baseline(db, 8_400, 0.01, days)
    conversion_series = seed_query_baseline(db, 3.4, 0.05, days)
    churn_series = seed_query_baseline(db, 1.6, 0.06, days)
    expense_series = seed_query_baseline(db, 940_000, 0.02, days)
    sales_series = seed_query_baseline(db, 2_160, 0.05, days)

    for i in range(days):
        ts = today - timedelta(days=days - 1 - i)
        prev_revenue = revenue_series[i - 1] if i > 0 else revenue_series[i]
        db.add(
            BusinessMetric(
                metric_date=ts,
                metric_type="revenue",
                value=revenue_series[i],
                previous_value=prev_revenue,
                change_pct=round((revenue_series[i] - prev_revenue) / prev_revenue * 100, 2),
                department="All",
                region="All",
                product="All",
                segment="All",
            )
        )
        db.add(
            BusinessMetric(
                metric_date=ts,
                metric_type="customers",
                value=customers_series[i],
                previous_value=customers_series[i - 1] if i > 0 else customers_series[i],
                change_pct=round(random.uniform(-0.5, 0.8), 2),
                department="All",
                region="All",
                product="All",
                segment="All",
            )
        )
        db.add(
            BusinessMetric(
                metric_date=ts,
                metric_type="conversion",
                value=conversion_series[i],
                previous_value=conversion_series[i - 1] if i > 0 else conversion_series[i],
                change_pct=round(random.uniform(-3, 3), 2),
                department="All",
                region="All",
                product="All",
                segment="All",
            )
        )
        db.add(
            BusinessMetric(
                metric_date=ts,
                metric_type="churn",
                value=churn_series[i],
                previous_value=churn_series[i - 1] if i > 0 else churn_series[i],
                change_pct=round(random.uniform(-4, 4), 2),
                department="All",
                region="All",
                product="All",
                segment="All",
            )
        )
        db.add(
            BusinessMetric(
                metric_date=ts,
                metric_type="expenses",
                value=expense_series[i],
                previous_value=expense_series[i - 1] if i > 0 else expense_series[i],
                change_pct=round(random.uniform(-1.5, 1.5), 2),
                department="All",
                region="All",
                product="All",
                segment="All",
            )
        )
        db.add(
            BusinessMetric(
                metric_date=ts,
                metric_type="sales",
                value=sales_series[i],
                previous_value=sales_series[i - 1] if i > 0 else sales_series[i],
                change_pct=round(random.uniform(-4, 4), 2),
                department="All",
                region="All",
                product="All",
                segment="All",
            )
        )

        # Regional / product dimension rows for a subset of dates
        if i % 3 == 0:
            for region in REGIONS:
                v = revenue_series[i] * random.uniform(0.15, 0.5)
                db.add(
                    BusinessMetric(
                        metric_date=ts,
                        metric_type="revenue",
                        value=v,
                        previous_value=v * (1 + random.uniform(-0.06, 0.06)),
                        change_pct=round(random.uniform(-4, 4), 2),
                        department="All",
                        region=region,
                        product="All",
                        segment="All",
                    )
                )
            for product in PRODUCTS:
                v = revenue_series[i] * random.uniform(0.08, 0.3)
                db.add(
                    BusinessMetric(
                        metric_date=ts,
                        metric_type="revenue",
                        value=v,
                        previous_value=v * (1 + random.uniform(-0.06, 0.06)),
                        change_pct=round(random.uniform(-4, 4), 2),
                        department="All",
                        region="All",
                        product=product,
                        segment="All",
                    )
                )
    db.commit()


def _seed_system_metrics(db, days: int):
    if db.query(SystemMetric).count() > 0:
        return

    base_time = _utcnow().replace(minute=0, second=0, microsecond=0)
    for i in range(288):
        ts = base_time - timedelta(minutes=5 * (287 - i))
        cpu = _random_between(18, 62)
        memory = _random_between(45, 82)
        disk = _random_between(40, 70)
        api_latency = _random_between(80, 420)
        request_rate = _random_between(300, 2400)
        error_rate = _random_between(0.1, 3.5)
        for service in ["api", "frontend", "database", "ai-service", "auth"]:
            db.add(
                SystemMetric(
                    timestamp=ts,
                    service=service,
                    cpu_usage=cpu * random.uniform(0.6, 1.4),
                    memory_usage=memory * random.uniform(0.7, 1.2),
                    disk_usage=disk * random.uniform(0.6, 1.1),
                    api_latency_ms=api_latency * random.uniform(0.5, 1.8),
                    request_rate=request_rate * random.uniform(0.4, 1.6),
                    error_rate=error_rate * random.uniform(0.3, 1.5),
                    db_health="HEALTHY" if random.random() > 0.03 else "DEGRADED",
                    is_synthetic=True,
                )
            )
    db.commit()


def _seed_security_events(db, days: int):
    if db.query(SecurityEvent).count() > 0:
        return

    now = _utcnow()
    for i in range(90):
        ts = now - timedelta(hours=random.uniform(0, days * 24))
        db.add(
            SecurityEvent(
                timestamp=ts,
                event_type=random.choice(SECURITY_EVENT_TYPES),
                source=random.choice(
                    [
                        "auth-service",
                        "edge-gateway",
                        "vpn-gateway",
                        "office-365",
                        "sentinel",
                        "github",
                        "salesforce",
                    ]
                ),
                severity=random.choices(SEVERITIES, weights=[45, 30, 18, 7])[0],
                status=random.choices(["OPEN", "INVESTIGATING", "RESOLVED", "CLOSED"], weights=[25, 20, 30, 25])[0],
                description=f"Synthetic {random.choice(SECURITY_EVENT_TYPES).lower()} event detected",
                username=random.choice(
                    ["alex.morgan", "priya.sharma", "jordan.lee", "casey.wu", "sam.taylor", "unknown"]
                ),
                ip_address=f"{random.randint(10, 220)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}",
                is_synthetic=True,
            )
        )
    db.commit()


def _seed_incidents(db, days: int):
    if db.query(Incident).count() > 0:
        return

    titles = [
        ("API latency spike", "MEDIUM", "n8n api-gateway reported elevated p95 latency."),
        ("Database connection pool exhaustion", "HIGH", "Primary DB reached connection limit."),
        ("Failed login surge", "HIGH", "Multiple failed auth attempts from a single source."),
        ("AI service degraded", "MEDIUM", "Embedding service response times increased."),
        ("Frontend build failure", "LOW", "Deployment pipeline failed on production build."),
        ("Billing data inconsistency", "CRITICAL", "Discrepancy in daily revenue aggregation."),
        ("Log aggregator down", "LOW", "Central log ingestion stopped receiving events."),
        ("Customer reported downtime", "HIGH", "Three enterprise customers reported errors."),
    ]
    now = _utcnow()
    for i, (title, sev, desc) in enumerate(titles):
        created = now - timedelta(hours=random.uniform(1, days * 24))
        status = random.choices(
            INCIDENT_STATUSES, weights=[15, 20, 10, 30, 25]
        )[0]
        inc = Incident(
            incident_id=f"INC-{1000 + i}",
            title=title,
            description=desc,
            severity=sev,
            status=status,
            assigned_agent=random.choice(
                ["data", "devops", "security", "support", "analytics", "finance"]
            ),
            assignee=random.choice(
                ["DevOps Team", "Security Team", "SRE", "Support L2", "Finance Ops", "On-call"]
            ),
            root_cause="Identified during investigation" if status in ("Resolved", "Closed") else "",
            resolution=(
                "Service restarted and monitoring verified"
                if status in ("Resolved", "Closed")
                else ""
            ),
            created_at=created,
        )
        db.add(inc)
        db.flush()
        db.add(
            IncidentEvent(
                incident_id_fk=inc.id,
                timestamp=created,
                event_type="created",
                message=f"Incident {inc.incident_id} created: {title}",
                actor="system",
            )
        )
        if status in ("Investigating", "Awaiting Approval", "Resolved", "Closed"):
            db.add(
                IncidentEvent(
                    incident_id_fk=inc.id,
                    timestamp=created + timedelta(minutes=random.randint(3, 20)),
                    event_type="status",
                    message="Status changed to Investigating",
                    actor=inc.assigned_agent,
                )
            )
        if status in ("Resolved", "Closed"):
            db.add(
                IncidentEvent(
                    incident_id_fk=inc.id,
                    timestamp=created + timedelta(hours=random.randint(1, 10)),
                    event_type="resolved",
                    message=f"Resolved: {inc.resolution}",
                    actor=inc.assigned_agent,
                )
            )
    db.commit()


def _seed_agents(db):
    if db.query(Agent).count() > 0:
        return

    agents = [
        ("finance", "Finance Agent", "Revenue, expenses, profit, gross margin, and financial trends.", "finance"),
        ("sales", "Sales Agent", "Sales, new customer acquisition, enterprise deals, retention.", "sales"),
        ("marketing", "Marketing Agent", "Marketing spend efficiency, conversion rates, funnel health.", "marketing"),
        ("devops", "Operations Agent", "Infrastructure performance, cloud costs, latency, and reliability.", "operations"),
        ("support", "Customer/Support Agent", "Support tickets, high-priority cases, and customer sentiment.", "support"),
        ("hr", "HR Agent", "Headcount, attrition, and workforce metrics.", "hr"),
        ("risk", "Risk Agent", "Risk posture, security events, and cost exposure.", "risk"),
        ("market", "Market/External Factors Agent", "Market conditions, competitors, and external factors.", "market"),
        ("forecast", "Forecast Agent", "Projections and forward-looking estimates from observed trends.", "forecast"),
        ("security", "Security Agent", "Authentication logs, suspicious activity, and security events.", "security"),
    ]
    for key, name, desc, cap in agents:
        db.add(
            Agent(
                key=key,
                name=name,
                description=desc,
                capability=cap,
                status="IDLE",
                current_task="Standby — idle monitoring",
                success_rate=0.0,
                avg_response_ms=0,
                last_execution=None,
                executions_total=0,
                executions_success=0,
            )
        )
    db.commit()


def _seed_notifications(db):
    if db.query(Notification).count() > 0:
        return

    notes = [
        ("Revenue anomaly detected", "Daily revenue deviated 2.4% from forecast.", "analytics", "HIGH"),
        ("Critical incident created", "INC-1003 — Failed login surge requires attention.", "security", "CRITICAL"),
        ("AI analysis completed", "Churn analysis for Q3 has been generated.", "ai", "INFO"),
        ("Approval required", "AI recommendation awaits manager approval.", "approval", "MEDIUM"),
        ("Security alert", "Multiple failed logins detected for a user account.", "security", "HIGH"),
        ("Report generated", "Daily executive report is ready to view.", "reports", "INFO"),
    ]
    now = _utcnow()
    for i, (title, message, category, sev) in enumerate(notes):
        db.add(
            Notification(
                title=title,
                message=message,
                category=category,
                severity=sev,
                read=False,
                created_at=now - timedelta(hours=i * 3),
            )
        )
    db.commit()


def _seed_demo_report_if_missing(db):
    from ..models import Report

    if db.query(Report).count() == 0:
        db.add(
            Report(
                report_type="daily",
                title="Daily Executive Report (Demo)",
                summary="Synthetic executive summary generated from demo data.",
                content=json.dumps(
                    {
                        "summary": "Revenue is trending within expectations. One high-severity incident in the last 24h.",
                        "key_metrics": ["Revenue $1.24M", "Growth +1.8%", "Conversion 3.4%", "Churn 1.6%"],
                        "incidents": ["INC-1003 Failed login surge"],
                        "recommendations": ["Review authentication failure patterns", "Validate billing aggregation"],
                    }
                ),
                status="GENERATED",
                created_by="system",
                created_at=_utcnow(),
            )
        )
        db.commit()


def csv_download(rows: list[dict], headers: list[str], filename: str):
    """Create an in-memory CSV download response."""
    import io

    from fastapi.responses import StreamingResponse

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow({h: row.get(h, "") for h in headers})
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )