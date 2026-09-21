"""Notification endpoints: list, mark-read, mark-all-read."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database.session import get_db
from ..models import Notification, User
from .deps import get_current_user

router = APIRouter()


@router.get("")
def list_notifications(
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(Notification)
        .order_by(Notification.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return {
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "category": n.category,
                "severity": n.severity,
                "read": n.read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in rows
        ]
    }


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    n = db.query(Notification).filter(Notification.id == notification_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.read = True
    db.commit()
    return {"id": n.id, "read": True}


@router.post("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    db.query(Notification).filter(Notification.read == False).update({"read": True})
    db.commit()
    return {"status": "ok"}
