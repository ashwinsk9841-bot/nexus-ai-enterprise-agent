"""Dashboard overview endpoint aggregating health, business, and operational status."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database.session import get_db
from ..models import BusinessMetric, Incident, SecurityEvent, SystemMetric, ApprovalRequest
from .deps import get_current_user

router = APIRouter()


def _metric_series(db, metric_type, days=45, **filters):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(BusinessMetric.metric_date, BusinessMetric.value)
        .filter(
            BusinessMetric.metric_type == metric_type,
            BusinessMetric.metric_date >= since,
        )
        .all()
    )
    return [r for r in rows]


@router.get("/overview")
def overview(db: Session = Depends(get_db), _: object = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    day_start = now - timedelta(days=1)

    def latest_value(metric_type, **filters):
        row = (
            db.query(BusinessMetric.value)
            .filter(BusinessMetric.metric_type == metric_type, **filters)
            .order_by(BusinessMetric.metric_date.desc())
            .first()
        )
        return row[0] if row else 0

    def prev_of(metric_type):
        row = (
            db.query(BusinessMetric.previous_value)
            .filter(BusinessMetric.metric_type == metric_type)
            .order_by(BusinessMetric.metric_date.desc())
            .first()
        )
        return row[0] if row else 0

    revenue = latest_value("revenue")
    revenue_prev = prev_of("revenue")
    rev_change = ((revenue - revenue_prev) / revenue_prev * 100) if revenue_prev else 0

    customers = latest_value("customers")
    customers_prev = latest_value("customers") * 0.98 + 60
    cust_change = ((customers - customers_prev) / customers_prev * 100) if customers_prev else 0

    conversion = latest_value("conversion")
    growth = max(0, cust_change)

    open_incidents = db.query(Incident).filter(
        Incident.status.in_(["Detected", "Investigating", "Awaiting Approval"])
    ).count()

    critical_alerts = db.query(SecurityEvent).filter(
        SecurityEvent.severity.in_(["HIGH", "CRITICAL"]),
        SecurityEvent.status.in_(["OPEN", "INVESTIGATING"]),
    ).count()

    pending_actions = db.query(ApprovalRequest).filter(ApprovalRequest.status == "PENDING").count()

    resolved_issues = db.query(Incident).filter(
        Incident.status.in_(["Resolved", "Closed"]),
        Incident.updated_at >= day_start,
    ).count()

    # Health checks
    db_health = "HEALTHY"
    try:
        db.query(func.count(SystemMetric.id)).scalar()
    except Exception:
        db_health = "DEGRADED"

    api_health = "HEALTHY"
    ai_health = "HEALTHY"
    server_health = "HEALTHY"
    last_system = (
        db.query(SystemMetric)
        .order_by(SystemMetric.timestamp.desc())
        .first()
    )
    if last_system:
        if last_system.error_rate and last_system.error_rate > 3:
            api_health = "DEGRADED"
        if last_system.memory_usage and last_system.memory_usage > 85:
            server_health = "DEGRADED"

    # Trend series
    def series(metric_type, days=30):
        since = now - timedelta(days=days)
        rows = (
            db.query(BusinessMetric.metric_date, BusinessMetric.value)
            .filter(BusinessMetric.metric_type == metric_type, BusinessMetric.metric_date >= since)
            .order_by(BusinessMetric.metric_date.asc())
            .all()
        )
        return [(r[0].isoformat(), r[1]) for r in rows]

    latency_rows = (
        db.query(SystemMetric.timestamp, SystemMetric.api_latency_ms)
        .order_by(SystemMetric.timestamp.desc())
        .limit(120)
        .all()
    )[::-1]

    incident_trend = []
    since = now - timedelta(days=30)
    incident_days = (
        db.query(func.date(Incident.created_at), func.count(Incident.id))
        .filter(Incident.created_at >= since)
        .group_by(func.date(Incident.created_at))
        .all()
    )
    incident_by_day = {}
    for d, c in incident_days:
        key = d
        if hasattr(d, "isoformat"):
            key = d.isoformat()[:10]
        else:
            key = str(d)[:10]
        incident_by_day[key] = c

    labels = [r[0] for r in series("revenue")]
    revenue_series = [r[1] for r in series("revenue")]
    customers_series = [r[1] for r in series("customers")]
    latency_series = [r[1] for r in latency_rows]
    latency_labels = [r[0].isoformat() for r in latency_rows]
    inc_series = [incident_by_day.get(l[:10], 0) for l in labels]

    return {
        "health": {
            "api_health": api_health,
            "db_health": db_health,
            "server_health": server_health,
            "ai_service_health": ai_health,
            "demo_mode": True,
        },
        "business": {
            "total_revenue": revenue,
            "revenue_change": round(rev_change, 2),
            "growth": round(growth, 2),
            "conversion": round(conversion, 2),
            "active_customers": int(customers),
            "customer_change": round(cust_change, 2),
        },
        "operations": {
            "open_incidents": open_incidents,
            "critical_alerts": critical_alerts,
            "pending_actions": pending_actions,
            "resolved_issues": resolved_issues,
        },
        "trends": {
            "labels": labels,
            "revenue": revenue_series,
            "customers": customers_series,
            "latency": latency_series,
            "latency_labels": latency_labels,
            "incidents": inc_series,
        },
    }