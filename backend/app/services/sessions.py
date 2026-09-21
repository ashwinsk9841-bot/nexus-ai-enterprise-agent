"""Server-side session management (with JWT sid claims)."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as OrmSession

from ..core.config import settings
from ..models import Session

# Naive UTC datetime for SQLite compatibility (stores naive datetimes).
def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_user_session(
    db: OrmSession,
    *,
    user_id: int,
    token: str,
    remember: bool = False,
    ip: str = "",
    user_agent: str = "",
) -> Session:
    token_id = secrets.token_hex(16)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    minutes = (
        settings.SESSION_REMEMBER_DAYS * 24 * 60
        if remember
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    expires = _utcnow() + timedelta(minutes=minutes)
    row = Session(
        user_id=user_id,
        token_id=token_id,
        token_hash=token_hash,
        remember=remember,
        ip_address=ip[:64],
        user_agent=user_agent[:255],
        created_at=_utcnow(),
        expires_at=expires,
        last_seen=_utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def validate_session(db: OrmSession, token: str, session_id: int) -> bool:
    """A token is valid only if its session exists, is active, and matches."""
    try:
        row = db.get(Session, session_id)
    except Exception:
        return False
    if not row or row.revoked:
        return False
    if row.expires_at and row.expires_at < _utcnow():
        return False
    if not hashlib.sha256(token.encode("utf-8")).hexdigest() == row.token_hash:
        return False
    row.last_seen = _utcnow()
    db.commit()
    return True


def revoke_session(db: OrmSession, session_id: int) -> None:
    row = db.get(Session, session_id)
    if row:
        row.revoked = True
        db.commit()


def revoke_all_user_sessions(db: OrmSession, user_id: int) -> int:
    count = (
        db.query(Session)
        .filter(Session.user_id == user_id, Session.revoked == False)  # noqa: E712
        .update({"revoked": True})
    )
    db.commit()
    return count


def create_user_session_placeholder(
    db: OrmSession,
    *,
    user_id: int,
    remember: bool = False,
    ip: str = "",
    user_agent: str = "",
) -> Session:
    """Create a session row before the JWT is known so we can embed its ID as ``sid``."""
    minutes = (
        settings.SESSION_REMEMBER_DAYS * 24 * 60
        if remember
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    expires = _utcnow() + timedelta(minutes=minutes)
    row = Session(
        user_id=user_id,
        token_id=secrets.token_hex(16),
        token_hash="",
        remember=remember,
        ip_address=ip[:64],
        user_agent=user_agent[:255],
        created_at=_utcnow(),
        expires_at=expires,
        last_seen=_utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def finalize_session_token(db: OrmSession, session_id: int, token: str) -> None:
    """Write the real token hash once the JWT has been minted."""
    row = db.get(Session, session_id)
    if row:
        row.token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        db.commit()