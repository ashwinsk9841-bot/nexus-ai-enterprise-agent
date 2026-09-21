"""Admin console endpoints: dashboard stats, user management, audit, agents, settings."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..core.audit import write_audit
from ..core.config import settings
from ..core.security import hash_password, normalize_email, password_strength
from ..database.session import get_db
from ..models import (
    Agent,
    AgentConfig,
    AuditLog,
    BusinessMetric,
    Incident,
    KnowledgeDocument,
    Notification,
    Report,
    SecurityEvent,
    Session as UserSession,
    SystemMetric,
    SystemSetting,
    User,
)
from .deps import get_current_user, require_admin

router = APIRouter()


# ---- helpers ----------------------------------------------------------------

def _is_admin(user: User = Depends(require_admin)):
    return user


# ---- schemas ----------------------------------------------------------------

class UserRoleUpdate(BaseModel):
    role: str

class UserDisableRequest(BaseModel):
    is_active: bool

class AgentConfigUpdate(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    model: str | None = None
    name: str | None = None
    description: str | None = None

class SettingUpdate(BaseModel):
    value: str


# ---- admin dashboard --------------------------------------------------------

@router.get("/dashboard")
def admin_dashboard(_admin: User = Depends(_is_admin), db: Session = Depends(get_db)):
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar() or 0  # noqa
    total_agents = db.query(func.count(Agent.id)).scalar() or 0
    total_sessions = db.query(func.count(UserSession.id)).filter(UserSession.revoked == False).scalar() or 0  # noqa
    total_audit = db.query(func.count(AuditLog.id)).scalar() or 0
    total_incidents = db.query(func.count(Incident.id)).scalar() or 0
    open_incidents = db.query(func.count(Incident.id)).filter(
        Incident.status.in_(["Detected", "Investigating", "Awaiting Approval"])
    ).scalar() or 0
    total_knowledge = db.query(func.count(KnowledgeDocument.id)).scalar() or 0
    total_reports = db.query(func.count(Report.id)).scalar() or 0
    total_metrics = db.query(func.count(BusinessMetric.id)).scalar() or 0
    recent_logins = (
        db.query(func.count(UserSession.id))
        .filter(UserSession.created_at >= datetime.utcnow() - timedelta(days=1))
        .scalar() or 0
    )
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_agents": total_agents,
        "active_sessions": total_sessions,
        "total_audit_events": total_audit,
        "total_incidents": total_incidents,
        "open_incidents": open_incidents,
        "knowledge_documents": total_knowledge,
        "total_reports": total_reports,
        "business_metrics": total_metrics,
        "recent_logins_24h": recent_logins,
        "demo_mode": settings.DEMO_MODE,
    }


# ---- user management --------------------------------------------------------

@router.get("/users")
def list_users(
    page: int = 1,
    size: int = 50,
    search: str = "",
    _admin: User = Depends(_is_admin),
    db: Session = Depends(get_db),
):
    q = db.query(User)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (User.email.ilike(like)) | (User.username.ilike(like)) | (User.full_name.ilike(like))
        )
    total = q.count()
    users = q.order_by(User.id).offset((page - 1) * size).limit(size).all()
    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "full_name": u.full_name,
                "role": u.role,
                "is_active": u.is_active,
                "demo_account": u.demo_account,
                "organization": u.organization,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login": u.last_login.isoformat() if u.last_login else None,
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/users/{user_id}")
def get_user(user_id: int, _admin: User = Depends(_is_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    sessions = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id)
        .order_by(UserSession.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "demo_account": user.demo_account,
            "organization": user.organization,
            "must_change_password": user.must_change_password,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        },
        "sessions": [
            {
                "id": s.id,
                "token_id": s.token_id,
                "revoked": s.revoked,
                "remember": s.remember,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "last_seen": s.last_seen.isoformat() if s.last_seen else None,
            }
            for s in sessions
        ],
    }


@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    body: UserRoleUpdate,
    request: Request,
    admin: User = Depends(_is_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if body.role not in ("VIEWER", "ANALYST", "MANAGER", "ADMIN"):
        raise HTTPException(status_code=400, detail="Invalid role")
    old_role = user.role
    user.role = body.role
    db.commit()
    write_audit(
        user_id=str(admin.id),
        username=admin.username,
        action="UPDATE_USER_ROLE",
        resource=f"users/{user_id}",
        details=f"Changed role from {old_role} to {body.role}",
        ip=request.client.host if request.client else "",
    )
    return {"status": "ok"}


@router.put("/users/{user_id}/active")
def set_user_active(
    user_id: int,
    body: UserDisableRequest,
    request: Request,
    admin: User = Depends(_is_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = body.is_active
    db.commit()
    write_audit(
        user_id=str(admin.id),
        username=admin.username,
        action="UPDATE_USER_ACTIVE",
        resource=f"users/{user_id}",
        details=f"Set active={body.is_active}",
        ip=request.client.host if request.client else "",
    )
    return {"status": "ok"}


# ---- audit logs -------------------------------------------------------------

@router.get("/audit")
def list_audit_logs(
    page: int = 1,
    size: int = 50,
    action: str = "",
    user_id: int | None = None,
    _admin: User = Depends(_is_admin),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    total = q.count()
    logs = q.order_by(AuditLog.id.desc()).offset((page - 1) * size).limit(size).all()
    return {
        "logs": [
            {
                "id": l.id,
                "user_id": l.user_id,
                "username": l.username,
                "action": l.action,
                "resource": l.resource,
                "details": l.details,
                "ip_address": l.ip_address,
                "request_id": l.request_id,
                "result": l.result,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
        "total": total,
        "page": page,
        "size": size,
    }


# ---- agent config -----------------------------------------------------------

@router.get("/agents")
def list_agent_configs(_admin: User = Depends(_is_admin), db: Session = Depends(get_db)):
    agents = db.query(Agent).order_by(Agent.id).all()
    configs = {c.agent_key: c for c in db.query(AgentConfig).all()}
    return {
        "agents": [
            {
                "key": a.key,
                "name": a.name,
                "description": a.description,
                "capability": a.capability,
                "status": a.status,
                "enabled": configs.get(a.key, AgentConfig()).enabled if a.key in configs else True,
                "provider": (configs.get(a.key, AgentConfig()).provider or "") if a.key in configs else "",
                "model": (configs.get(a.key, AgentConfig()).model or "") if a.key in configs else "",
            }
            for a in agents
        ]
    }


@router.put("/agents/{agent_key}")
def update_agent_config(
    agent_key: str,
    body: AgentConfigUpdate,
    request: Request,
    admin: User = Depends(_is_admin),
    db: Session = Depends(get_db),
):
    config = db.query(AgentConfig).filter(AgentConfig.agent_key == agent_key).first()
    if not config:
        agent = db.query(Agent).filter(Agent.key == agent_key).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        config = AgentConfig(
            agent_key=agent_key,
            name=agent.name,
            description=agent.description,
            capability=agent.capability,
        )
        db.add(config)
    if body.enabled is not None:
        config.enabled = body.enabled
    if body.provider is not None:
        config.provider = body.provider
    if body.model is not None:
        config.model = body.model
    if body.name is not None:
        config.name = body.name
    if body.description is not None:
        config.description = body.description
    config.updated_at = datetime.utcnow()
    db.commit()
    write_audit(
        user_id=str(admin.id),
        username=admin.username,
        action="UPDATE_AGENT_CONFIG",
        resource=f"agents/{agent_key}",
        details=f"Updated config: enabled={config.enabled}, provider={config.provider}, model={config.model}",
        ip=request.client.host if request.client else "",
    )
    return {"status": "ok"}


# ---- system settings --------------------------------------------------------

@router.get("/settings")
def list_settings(_admin: User = Depends(_is_admin), db: Session = Depends(get_db)):
    settings_rows = db.query(SystemSetting).all()
    return {"settings": {s.key: s.value for s in settings_rows}}


@router.put("/settings/{key}")
def update_setting(
    key: str,
    body: SettingUpdate,
    request: Request,
    admin: User = Depends(_is_admin),
    db: Session = Depends(get_db),
):
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        row = SystemSetting(key=key, value=body.value)
        db.add(row)
    else:
        row.value = body.value
    db.commit()
    write_audit(
        user_id=str(admin.id),
        username=admin.username,
        action="UPDATE_SETTING",
        resource=f"settings/{key}",
        details=f"Value={body.value[:200]}",
        ip=request.client.host if request.client else "",
    )
    return {"status": "ok"}


# ---- provider metadata ------------------------------------------------------

@router.get("/providers")
def list_providers(_admin: User = Depends(_is_admin)):
    from ..ai.providers import available_provider_metadata
    return {"providers": available_provider_metadata()}


# ---- knowledge docs ---------------------------------------------------------

@router.get("/knowledge")
def list_knowledge_docs(_admin: User = Depends(_is_admin), db: Session = Depends(get_db)):
    docs = db.query(KnowledgeDocument).order_by(KnowledgeDocument.id.desc()).all()
    return {
        "documents": [
            {
                "id": d.id,
                "title": d.title,
                "filename": d.filename,
                "doc_type": d.doc_type,
                "size_bytes": d.size_bytes,
                "status": d.status,
                "chunk_count": d.chunk_count,
                "uploaded_by": d.uploaded_by,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    }


# ---- security events --------------------------------------------------------

@router.get("/security-events")
def list_security_events(
    page: int = 1,
    size: int = 50,
    severity: str = "",
    _admin: User = Depends(_is_admin),
    db: Session = Depends(get_db),
):
    q = db.query(SecurityEvent)
    if severity:
        q = q.filter(SecurityEvent.severity == severity.upper())
    total = q.count()
    events = q.order_by(SecurityEvent.id.desc()).offset((page - 1) * size).limit(size).all()
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
            }
            for e in events
        ],
        "total": total,
        "page": page,
        "size": size,
    }


# ---- system health ----------------------------------------------------------

@router.get("/health")
def system_health(_admin: User = Depends(_is_admin)):
    try:
        from ..database.session import engine as _eng
        with _eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "database": "HEALTHY" if db_ok else "UNREACHABLE",
        "ai_configured": bool(settings.OPENAI_API_KEY),
        "demo_mode": settings.DEMO_MODE,
        "environment": settings.ENVIRONMENT,
    }
