"""AI Command Center endpoint — multi-agent orchestration."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..services.orchestrator import Orchestrator
from ..models import User
from .deps import get_current_user

router = APIRouter()


class CommandRequest(BaseModel):
    query: str


@router.post("/command")
def command(body: CommandRequest, user: User = Depends(get_current_user)):
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    orch = Orchestrator(user_id=str(user.id), username=user.username)
    result = orch.run(body.query)
    return result


@router.get("/conversations")
def conversations(user: User = Depends(get_current_user)):
    from ..database.session import SessionLocal
    from ..models import AIConversation

    db = SessionLocal()
    try:
        rows = (
            db.query(AIConversation)
            .filter(AIConversation.user_id == str(user.id))
            .order_by(AIConversation.created_at.desc())
            .limit(50)
            .all()
        )
        return {
            "conversations": [
                {
                    "id": c.id,
                    "session_id": c.session_id,
                    "title": c.title,
                    "query": c.query,
                    "agents_used": c.agents_used,
                    "result": c.result[:500],
                    "status": c.status,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in rows
            ]
        }
    finally:
        db.close()
