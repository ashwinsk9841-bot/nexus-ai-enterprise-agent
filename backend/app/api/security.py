"""Security center endpoints: summary, event list."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database.session import get_db
from ..models import SecurityEvent
from .deps import get_current_user

router = APIRouter()


@router.get("/summary")
def summary(db: Session = Depends(get_db), _=Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    day_start = now - timedelta(days=1)
    events_last_day = db.query(SecurityEvent).filter(SecurityEvent.timestamp >= day_start)
    failed = events_last_day.filter(SecurityEvent.event_type == "Failed login").count()
    suspicious = events_last_day.filter(SecurityEvent.severity.in_(["HIGH", "CRITICAL"])).count()
    active_alerts = db.query(SecurityEvent).filter(SecurityEvent.status == "OPEN").count()

    severity_counts = dict(
        db.query(SecurityEvent.severity, func.count(SecurityEvent.id))
        .group_by(SecurityEvent.severity)
        .all()
    )

    total = sum(severity_counts.values()) or 1
    critical_weight = (severity_counts.get("CRITICAL", 0) * 4 + severity_counts.get("HIGH", 0) * 2) / total
    score = max(45, int(100 - critical_weight * 15))

    risk = "HIGH" if critical_weight > 1.5 else "ELEVATED" if critical_weight > 0.7 else "NORMAL"

    return {
        "summary": {
            "security_score": score,
            "failed_logins": failed,
            "suspicious_events": suspicious,
            "active_alerts": active_alerts,
            "risk_level": risk,
            "by_severity": {k: severity_counts.get(k, 0) for k in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
        }
    }


@router.get("/events")
def events(
    severity: str = "All",
    status: str = "All",
    limit: int = 60,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(SecurityEvent)
    if severity != "All":
        q = q.filter(SecurityEvent.severity == severity)
    if status != "All":
        q = q.filter(SecurityEvent.status == status)

    rows = q.order_by(SecurityEvent.timestamp.desc()).limit(min(limit, 150)).all()
    return {
        "events": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "event_type": e.event_type,
                "source": e.source,
                "severity": e.severity,
                "status": e.status,
                "description": e.description,
                "username": e.username,
                "ip_address": e.ip_address,
                "is_synthetic": e.is_synthetic,
            }
            for e in rows
        ]
    }