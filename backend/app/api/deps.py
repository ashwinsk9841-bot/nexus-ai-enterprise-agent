"""Shared FastAPI dependencies: auth, RBAC, pagination helpers."""

from fastapi import Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session

from ..core.security import decode_access_token, is_admin_role, role_at_least
from ..database.session import get_db
from ..models import User


def get_current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from a Bearer token.

    When the token carries a ``sid`` claim the corresponding server-side
    session is validated (active, not revoked, not expired, hash matches).
    Tokens without ``sid`` (e.g. pre-upgrade or test tokens) are accepted
    for backward compatibility.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # --- session check (optional for old tokens) ----------------------------
    sid = payload.get("sid")
    if sid is not None:
        from ..services.sessions import validate_session

        if not validate_session(db, token, int(sid)):
            raise HTTPException(
                status_code=401,
                detail="Session revoked, expired, or token mismatch",
            )

    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or deactivated")
    return user


def require_role(min_role: str):
    """Factory for role-based dependency guard."""

    def checker(user: User = Depends(get_current_user)):
        if not role_at_least(user.role, min_role):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker


require_admin = require_role("ADMIN")


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""
