"""Audit logging helper."""

import logging
from datetime import datetime, timezone

from ..database.session import SessionLocal
from ..models import AuditLog

logger = logging.getLogger("nexus.audit")


def write_audit(
    *,
    user_id: str,
    username: str,
    action: str,
    resource: str,
    details: str = "",
    ip: str = "",
    request_id: str = "",
    result: str = "SUCCESS",
):
    """Persist an audit log entry."""
    try:
        db = SessionLocal()
        entry = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            resource=resource,
            details=details[:2000],
            ip_address=ip[:64],
            request_id=request_id[:64],
            result=result[:32],
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        db.commit()
        db.close()
    except Exception:
        logger.exception("Failed to write audit log: %s / %s", action, resource)
        try:
            db.close()
        except Exception:
            pass