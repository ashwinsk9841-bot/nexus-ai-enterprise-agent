"""Report generation: executive, security, operations, incidents."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai.service import ai_chat, openai_available
from ..database.session import get_db
from ..models import Report, BusinessMetric, SecurityEvent, Incident
from .deps import get_current_user

router = APIRouter()


class ReportRequest(BaseModel):
    report_type: str = "daily"
    date_range: int = 30


@router.get("")
def list_reports(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.query(Report).order_by(Report.created_at.desc()).limit(40).all()
    return {
        "reports": [
            {
                "id": r.id,
                "report_type": r.report_type,
                "title": r.title,
                "summary": r.summary,
                "status": r.status,
                "created_by": r.created_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.post("/generate")
def generate(body: ReportRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # Gather context
    rev_rows = (
        db.query(BusinessMetric.metric_date, BusinessMetric.value)
        .filter(BusinessMetric.metric_type == "revenue")
        .order_by(BusinessMetric.metric_date.desc())
        .limit(body.date_range)
        .all()
    )
    rev_first = rev_rows[-1][1] if rev_rows else 100000
    rev_last = rev_rows[0][1] if rev_rows else 100000
    rev_change = ((rev_last - rev_first) / rev_first * 100) if rev_first else 0

    cust_rows = (
        db.query(BusinessMetric.value)
        .filter(BusinessMetric.metric_type == "customers")
        .order_by(BusinessMetric.metric_date.desc())
        .limit(body.date_range)
        .all()
    )
    customers = cust_rows[0][0] if cust_rows else 0

    sec_critical = db.query(SecurityEvent).filter(SecurityEvent.severity == "CRITICAL").count()
    open_inc = db.query(Incident).filter(Incident.status.in_(["Detected", "Investigating"])).count()

    summary = (
        f"Revenue trended {'up' if rev_change >= 0 else 'down'} {abs(rev_change):.1f}% over the period "
        f"(${rev_last:,.0f} latest). Active customer base: {int(customers):,}. "
        f"{sec_critical} critical security events and {open_inc} open incidents require attention."
    )

    if body.report_type == "security":
        summary = (
            f"Security posture: {sec_critical} critical security events recorded. "
            "Review flagged anomalies and ensure incident response runbooks are current."
        )
    elif body.report_type == "operations":
        summary = (
            "Infrastructure health is within nominal parameters. "
            "API latency and error rates have remained stable. No incidents required escalation."
        )
    elif body.report_type == "incidents":
        summary = (
            f"Current operational impact: {open_inc} open incidents. "
            "Recommend reviewing root-cause documents and running AI analysis for unresolved items."
        )

    title = {
        "daily": "Daily Executive Report",
        "weekly": "Weekly Business Report",
        "security": "Security Report",
        "operations": "Operations Report",
        "incidents": "AI Incident Report",
    }.get(body.report_type, f"{body.report_type.title()} Report") + f" — {datetime.now(timezone.utc).strftime('%b %d, %Y')}"

    content = json.dumps({
        "summary": summary,
        "key_metrics": [
            f"Revenue ${rev_last:,.0f} ({rev_change:+.1f}%)",
            f"Customers {int(customers):,}",
            f"Critical security events {sec_critical}",
            f"Open incidents {open_inc}",
        ],
        "changes": [
            f"Revenue {'increased' if rev_change >= 0 else 'decreased'} {abs(rev_change):.1f}% over period",
            f"{sec_critical} security events flagged as CRITICAL",
        ],
        "incidents": [
            f"{open_inc} incidents currently in Detected or Investigating status",
        ],
        "root_causes": [
            "Trend drivers include regional sales variation and seasonal effects",
            "Security events primarily sourced from failed login attempts",
        ],
        "recommendations": [
            "Review weekly revenue trend and regional performance",
            "Ensure critical security events are triaged and resolved",
            "Update runbooks and review incident root causes",
            "Generate a drill-down report on flagged metrics",
        ],
    }, indent=2)

    report = Report(
        report_type=body.report_type,
        title=title,
        summary=summary,
        content=content,
        status="GENERATED",
        created_by=user.username,
        created_at=datetime.now(timezone.utc),
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return {
        "report": {
            "id": report.id,
            "report_type": report.report_type,
            "title": report.title,
            "summary": report.summary,
            "content": report.content,
            "status": report.status,
            "created_by": report.created_by,
            "created_at": report.created_at.isoformat(),
        }
    }


@router.post("/{report_id}/export")
def export_pdf(report_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    content = report.content
    try:
        content = json.loads(content)
    except json.JSONDecodeError:
        content = {"summary": content}

    html = f"""
    <html><head><title>{report.title}</title></head>
    <body style="font-family:Inter,sans-serif;padding:32px;max-width:800px;margin:auto">
      <h1 style="font-size:22px">{report.title}</h1>
      <p><em>Generated by {report.created_by} on {report.created_at.strftime('%b %d, %Y %H:%M UTC') if report.created_at else 'N/A'}</em></p>
      <h3>Executive Summary</h3>
      <p>{content.get('summary', '')}</p>
      {"<h3>Key Metrics</h3><ul>" + "".join(f"<li>{m}</li>" for m in content.get('key_metrics', [])) + "</ul>" if content.get('key_metrics') else ""}
      {"<h3>Recommendations</h3><ul>" + "".join(f"<li>{r}</li>" for r in content.get('recommendations', [])) + "</ul>" if content.get('recommendations') else ""}
    </body></html>"""
    return {"html": html, "content": content}