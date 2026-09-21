"""Operations center: system metrics for CPU/memory/disk/API/requests/errors."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database.session import get_db
from ..models import SystemMetric
from .deps import get_current_user

router = APIRouter()


@router.get("/metrics")
def metrics(
    service: str = "api",
    minutes: int = 60,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    minutes = max(15, min(minutes, 1440))
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    rows = (
        db.query(SystemMetric)
        .filter(SystemMetric.service == service, SystemMetric.timestamp >= since)
        .order_by(SystemMetric.timestamp.asc())
        .limit(400)
        .all()
    )

    # Down-sample if needed
    step = max(1, len(rows) // 100)
    sampled = rows[::step] if step > 1 else rows

    def series(attr):
        return [round(getattr(r, attr, 0) or 0, 1) for r in sampled]

    latest = rows[-1] if rows else None

    return {
        "labels": [r.timestamp.isoformat() for r in sampled],
        "metrics": {
            "cpu_usage": series("cpu_usage"),
            "memory_usage": series("memory_usage"),
            "disk_usage": series("disk_usage"),
            "api_latency_ms": series("api_latency_ms"),
            "request_rate": series("request_rate"),
            "error_rate": series("error_rate"),
        },
        "latest": {
            "cpu_usage": round(latest.cpu_usage, 1) if latest else 0,
            "memory_usage": round(latest.memory_usage, 1) if latest else 0,
            "disk_usage": round(latest.disk_usage, 1) if latest else 0,
            "api_latency_ms": round(latest.api_latency_ms, 1) if latest else 0,
            "request_rate": round(latest.request_rate, 1) if latest else 0,
            "error_rate": round(latest.error_rate, 1) if latest else 0,
            "db_health": latest.db_health if latest else "HEALTHY",
        },
        "service": service,
        "minutes": minutes,
    }