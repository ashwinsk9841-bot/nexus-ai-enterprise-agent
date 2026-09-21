"""Human-approval endpoints for sensitive AI actions."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database.session import get_db
from ..models import ApprovalRequest, User
from ..core.audit import write_audit
from ..core.security import role_at_least
from .deps import get_current_user, require_role

router = APIRouter()


class ApprovalDecision(BaseModel):
    decision: str  # APPROVED or REJECTED
    note: str = ""


@router.get("")
def list_approvals(
    status: str = "All",
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(ApprovalRequest)
    if status != "All":
        q = q.filter(ApprovalRequest.status == status)

    rows = q.order_by(ApprovalRequest.created_at.desc()).limit(100).all()
    return {
        "approvals": [
            {
                "id": a.id,
                "title": a.title,
                "action": a.action,
                "reason": a.reason,
                "expected_result": a.expected_result,
                "risk_level": a.risk_level,
                "affected_service": a.affected_service,
                "system_response": a.system_response,
                "status": a.status,
                "requested_by": a.requested_by,
                "decided_by": a.decided_by,
                "decision_note": a.decision_note,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "decided_at": a.decided_at.isoformat() if a.decided_at else None,
            }
            for a in rows
        ]
    }


@router.get("/{approval_id}")
def approval_detail(
    approval_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    a = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {
        "id": a.id,
        "title": a.title,
        "action": a.action,
        "reason": a.reason,
        "expected_result": a.expected_result,
        "risk_level": a.risk_level,
        "affected_service": a.affected_service,
        "system_response": a.system_response,
        "status": a.status,
        "requested_by": a.requested_by,
        "decided_by": a.decided_by,
        "decision_note": a.decision_note,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
    }


@router.post("/{approval_id}/decide")
def decide_approval(
    approval_id: int,
    body: ApprovalDecision,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("MANAGER")),
):
    a = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if a.status != "PENDING":
        raise HTTPException(status_code=400, detail="This request has already been decided")

    if body.decision not in ("APPROVED", "REJECTED"):
        raise HTTPException(status_code=400, detail="Decision must be APPROVED or REJECTED")

    a.status = body.decision
    a.decided_by = user.username
    a.decision_note = body.note
    a.decided_at = datetime.now(timezone.utc)
    db.commit()

    write_audit(
        user_id=str(user.id),
        username=user.username,
        action=f"APPROVAL_{body.decision}",
        resource=f"approval:{a.id}",
        details=f"{a.title} — {body.note}",
    )

    return {"id": a.id, "status": a.status}
