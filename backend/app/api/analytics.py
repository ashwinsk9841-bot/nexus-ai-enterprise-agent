"""Analytics endpoints: filtered metrics, AI explanation, CSV export."""

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai.service import ai_chat, openai_available
from ..database.session import get_db, SessionLocal
from ..models import BusinessMetric
from .deps import get_current_user

router = APIRouter()

METRIC_TYPES = ["revenue", "sales", "customers", "conversion", "churn", "expenses"]


@router.get("/metrics")
def get_metrics(
    days: int = 30,
    department: str = "All",
    region: str = "All",
    product: str = "All",
    segment: str = "All",
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    metrics = {}
    labels = None
    for mtype in METRIC_TYPES:
        q = db.query(BusinessMetric).filter(
            BusinessMetric.metric_type == mtype,
            BusinessMetric.metric_date >= since,
        )
        if department != "All":
            q = q.filter(BusinessMetric.department == department)
        if region != "All":
            q = q.filter(BusinessMetric.region == region)
        if product != "All":
            q = q.filter(BusinessMetric.product == product)
        if segment != "All":
            q = q.filter(BusinessMetric.segment == segment)

        rows = q.order_by(BusinessMetric.metric_date.asc()).all()
        if not rows:
            continue
        day_map = {}
        for r in rows:
            key = r.metric_date.isoformat()[:10]
            day_map[key] = (day_map.get(key, 0) + (r.value or 0)) / (1 if key not in day_map else 2)
        ordered = sorted(day_map.items())
        values = [v for _, v in ordered]
        labels = labels or [k + "T00:00:00" for k, _ in ordered]
        first = values[0] if values else 0
        last = values[-1] if values else 0
        metrics[mtype] = {
            "values": [round(v, 2) for v in values],
            "change_pct": round(((last - first) / first) * 100, 2) if first else 0,
            "min": round(min(values), 2) if values else 0,
            "max": round(max(values), 2) if values else 0,
        }

    return {
        "labels": labels or [],
        "metrics": metrics,
        "filters": {"days": days, "department": department, "region": region, "product": product, "segment": segment},
    }


class ExplainRequest(BaseModel):
    days: int = 30
    department: str = "All"
    region: str = "All"
    product: str = "All"
    segment: str = "All"


@router.post("/export")
def export_csv(
    data: ExplainRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    since = datetime.now(timezone.utc) - timedelta(days=data.days)
    q = db.query(BusinessMetric).filter(BusinessMetric.metric_date >= since)
    if data.department != "All":
        q = q.filter(BusinessMetric.department == data.department)
    if data.region != "All":
        q = q.filter(BusinessMetric.region == data.region)
    if data.product != "All":
        q = q.filter(BusinessMetric.product == data.product)
    if data.segment != "All":
        q = q.filter(BusinessMetric.segment == data.segment)

    rows = q.order_by(BusinessMetric.metric_date.asc()).all()
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["date", "metric", "value", "department", "region", "product", "segment", "change_pct"],
    )
    writer.writeheader()
    for r in rows:
        writer.writerow(
            {
                "date": r.metric_date.isoformat(),
                "metric": r.metric_type,
                "value": r.value,
                "department": r.department,
                "region": r.region,
                "product": r.product,
                "segment": r.segment,
                "change_pct": r.change_pct,
            }
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=nexus-analytics.csv"},
    )


@router.post("/explain")
def explain(data: ExplainRequest, _=Depends(get_current_user)):
    db = SessionLocal()
    try:
        metrics = get_metrics(
            days=data.days,
            department=data.department,
            region=data.region,
            product=data.product,
            segment=data.segment,
            db=db,
            _=_,
        )
    finally:
        db.close()

    summary_lines = []
    for mtype, series in (metrics["metrics"] or {}).items():
        vals = series.get("values", [])
        if not vals:
            continue
        summary_lines.append(
            f"{mtype}: start={vals[0]:.2f}, end={vals[-1]:.2f}, change={series['change_pct']:+.2f}%, min={series['min']:.2f}, max={series['max']:.2f}"
        )

    if not summary_lines:
        return {"explanation": "No metric data available for the selected filters."}

    if not openai_available():
        explanation = (
            "Data inspection (demo mode):\n" + "\n".join(summary_lines)
        )
    else:
        prompt = (
            "You are a senior business analyst at NEXUS. Explain the key trends in the chart "
            "data below. Point out the most significant moves, possible drivers, and what to "
            "watch. Be concise and data-driven.\n\nDATA:\n"
            + "\n".join(summary_lines)
        )
        try:
            explanation = ai_chat(
                [{"role": "system", "content": "You are a concise senior business analyst."},
                 {"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=700,
            )
        except Exception:
            explanation = "Data inspection:\n" + "\n".join(summary_lines)

    # Persist a report-like notification
    try:
        from ..core.audit import write_audit
    except Exception:
        pass

    return {"explanation": explanation}

