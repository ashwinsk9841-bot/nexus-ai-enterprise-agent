"""Agent registry, status, execution-history, and provider/model/confidence endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database.session import get_db
from ..models import Agent, AgentConfig, AgentRun
from .deps import get_current_user

router = APIRouter()


def _agent_dict(a: Agent, config: AgentConfig | None = None) -> dict:
    cfg = config or AgentConfig()
    return {
        "id": a.id,
        "key": a.key,
        "name": a.name,
        "description": a.description,
        "capability": a.capability,
        "status": a.status,
        "current_task": a.current_task,
        "success_rate": a.success_rate,
        "avg_response_ms": a.avg_response_ms,
        "last_execution": a.last_execution.isoformat() if a.last_execution else None,
        "executions_total": a.executions_total,
        "executions_success": a.executions_success,
        "provider": cfg.provider or "",
        "model": cfg.model or "",
        "enabled": cfg.enabled if hasattr(cfg, "enabled") else True,
    }


@router.get("")
def list_agents(db: Session = Depends(get_db), _=Depends(get_current_user)):
    agents = db.query(Agent).order_by(Agent.id).all()
    configs = {c.agent_key: c for c in db.query(AgentConfig).all()}
    return {
        "agents": [_agent_dict(a, configs.get(a.key)) for a in agents]
    }


@router.get("/{agent_id}")
def agent_detail(agent_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    config = db.query(AgentConfig).filter(AgentConfig.agent_key == agent.key).first()
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.agent_id == agent_id)
        .order_by(AgentRun.started_at.desc())
        .limit(50)
        .all()
    )
    return {
        "agent": _agent_dict(agent, config),
        "runs": [
            {
                "id": r.id,
                "query": r.query,
                "task": r.task,
                "status": r.status,
                "error_message": r.error_message,
                "duration_ms": r.duration_ms,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in runs
        ],
    }
