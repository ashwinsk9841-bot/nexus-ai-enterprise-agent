"""Incident management CRUD endpoints."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database.session import get_db
from ..models import Incident, IncidentEvent
from .deps import get_current_user

router = APIRouter()


class IncidentCreate(BaseModel):
    title: str = ""
    description: str = ""
    severity: str = "LOW"
    status: str = "Detected"
    assigned_agent: str = ""
    assignee: str = ""
    root_cause: str = ""
    resolution: str = ""


@router.get("")
def list_incidents(
    status: str = "All",
    severity: str = "All",
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(Incident)
    if status != "All":
        q = q.filter(Incident.status == status)
    if severity != "All":
        q = q.filter(Incident.severity == severity)

    rows = q.order_by(Incident.created_at.desc()).limit(100).all()
    return {
        "incidents": [
            {
                "id": inc.id,
                "incident_id": inc.incident_id,
                "title": inc.title,
                "description": inc.description,
                "severity": inc.severity,
                "status": inc.status,
                "assigned_agent": inc.assigned_agent,
                "assignee": inc.assignee,
                "root_cause": inc.root_cause,
                "resolution": inc.resolution,
                "created_at": inc.created_at.isoformat() if inc.created_at else None,
                "updated_at": inc.updated_at.isoformat() if inc.updated_at else None,
            }
            for inc in rows
        ]
    }


@router.get("/{incident_id}")
def detail(incident_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    events = db.query(IncidentEvent).filter(IncidentEvent.incident_id_fk == inc.id).order_by(IncidentEvent.timestamp).all()
    return {
        "id": inc.id,
        "incident_id": inc.incident_id,
        "title": inc.title,
        "description": inc.description,
        "severity": inc.severity,
        "status": inc.status,
        "assigned_agent": inc.assigned_agent,
        "assignee": inc.assignee,
        "root_cause": inc.root_cause,
        "resolution": inc.resolution,
        "created_at": inc.created_at.isoformat() if inc.created_at else None,
        "updated_at": inc.updated_at.isoformat() if inc.updated_at else None,
        "events": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "event_type": e.event_type,
                "message": e.message,
                "actor": e.actor,
            }
            for e in events
        ],
    }


@router.post("")
def create_incident(body: IncidentCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    inc_id = f"INC-{uuid.uuid4().hex[:5].upper()}"
    inc = Incident(
        incident_id=inc_id,
        title=body.title,
        description=body.description,
        severity=body.severity,
        status=body.status,
        assigned_agent=body.assigned_agent,
        assignee=body.assignee,
        root_cause=body.root_cause,
        resolution=body.resolution,
        created_at=datetime.now(timezone.utc),
    )
    db.add(inc)
    db.flush()
    db.add(
        IncidentEvent(
            incident_id_fk=inc.id,
            timestamp=datetime.now(timezone.utc),
            event_type="created",
            message=f"Incident created: {body.title}",
            actor=user.username,
        )
    )
    db.commit()
    return {"id": inc.id, "incident_id": inc.incident_id, "status": "created"}


@router.patch("/{incident_id}")
def update_incident(
    incident_id: int,
    body: IncidentCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    old_status = inc.status
    if body.title:
        inc.title = body.title
    if body.description:
        inc.description = body.description
    if body.severity:
        inc.severity = body.severity
    if body.status:
        inc.status = body.status
    if body.assigned_agent:
        inc.assigned_agent = body.assigned_agent
    if body.assignee:
        inc.assignee = body.assignee
    if body.root_cause:
        inc.root_cause = body.root_cause
    if body.resolution:
        inc.resolution = body.resolution
    inc.updated_at = datetime.now(timezone.utc)

    if body.status and body.status != old_status:
        db.add(
            IncidentEvent(
                incident_id_fk=inc.id,
                timestamp=datetime.now(timezone.utc),
                event_type="status",
                message=f"Status changed to {body.status}",
                actor=user.username,
            )
        )

    db.commit()
    return {"id": inc.id, "status": "updated"}