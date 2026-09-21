"""Authentication endpoints: register, login, me, logout.

Security model:
- Passwords are hashed (PBKDF2-SHA256), never stored or logged in plaintext.
- Registration automatically signs the new user in (no email verification).
- Login requires a correct email + password; there is no verification gate.
- Session tokens are server-side tracked (revocable, remember-me aware).
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..core.audit import write_audit
from ..core.config import settings
from ..core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    normalize_email,
    password_strength,
    validate_email,
    verify_password,
)
from ..database.session import get_db
from ..models import Session as UserSession, User
from ..services.limiter import (
    clear_login,
    is_login_rate_limited,
    limit_generic,
    limit_login,
)
from ..services.sessions import (
    create_user_session_placeholder,
    finalize_session_token,
    revoke_session,
)
from .deps import get_current_user

logger = logging.getLogger("nexus.auth")

router = APIRouter()


# ---- schemas ---------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str
    remember: bool = False


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    full_name: str
    role: str
    demo_account: bool
    organization: str
    must_change_password: bool

    model_config = {"from_attributes": True}


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    full_name: str
    password: str
    confirm_password: str = ""


# ---- helpers ---------------------------------------------------------------

def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    masked = local[0] + "***" if local else "***"
    return f"{masked}@{domain}"


def _issue_session(
    db: Session, user: User, *, ip: str, user_agent: str, remember: bool = False
) -> str:
    """Create a tracked server-side session + JWT for ``user`` and sign them in."""
    placeholder = create_user_session_placeholder(
        db,
        user_id=user.id,
        remember=remember,
        ip=ip,
        user_agent=user_agent,
    )
    token = create_access_token(
        subject=user.email,
        role=user.role,
        username=user.username,
        session_id=placeholder.id,
        remember=remember,
    )
    finalize_session_token(db, placeholder.id, token)
    user.last_login = _utcnow()
    db.commit()
    return token


# ---- auth configuration ----------------------------------------------------

@router.get("/config")
def auth_config():
    """Public, non-sensitive auth configuration used by the login screens."""
    return {
        "signup_enabled": settings.ALLOW_SIGNUP,
        "environment": settings.ENVIRONMENT,
        "demo_login_enabled": settings.DEMO_MODE,
    }


# ---- registration ------------------------------------------------------------

@router.post("/register")
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    if not settings.ALLOW_SIGNUP:
        raise HTTPException(status_code=403, detail="Public registration is disabled")

    ip = request.client.host if request.client else ""
    if not limit_generic(f"register:{ip}", max_requests=10, window_seconds=3600):
        raise HTTPException(
            status_code=429,
            detail="Too many registration attempts. Please try again later.",
        )

    email = normalize_email(body.email)
    if not validate_email(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    if not body.full_name.strip():
        raise HTTPException(status_code=400, detail="Full name is required.")
    if len(body.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email already registered. Please sign in.",
        )
    if db.query(User).filter(User.username == body.username.strip()).first():
        raise HTTPException(status_code=409, detail="Username already taken")
    if body.confirm_password and body.password != body.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    issues = password_strength(body.password)
    if issues:
        raise HTTPException(status_code=400, detail="; ".join(issues))

    user = User(
        email=email,
        username=body.username.strip(),
        full_name=body.full_name.strip(),
        hashed_password=hash_password(body.password),
        role="VIEWER",
        is_active=True,
        demo_account=False,
    )
    db.add(user)
    db.flush()

    # The new account is signed in immediately — no verification step.
    token = _issue_session(
        db,
        user,
        ip=ip,
        user_agent=(request.headers.get("user-agent") or "")[:255],
    )

    write_audit(
        user_id=str(user.id),
        username=user.username,
        action="REGISTER",
        resource="auth",
        details=f"New account registered ({_mask_email(email)})",
        request_id=request.headers.get("x-request-id", ""),
    )
    return {
        "status": "ok",
        "message": "Account created.",
        "access_token": token,
        "token_type": "bearer",
        "user": UserOut.model_validate(user).model_dump(),
    }


# ---- session ------------------------------------------------------------------

@router.post("/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = normalize_email(body.email)
    ip = request.client.host if request.client else ""
    _check_login_rate_limit(ip, email)

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        limit_login(ip, scope=email)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = _issue_session(
        db,
        user,
        ip=ip,
        user_agent=(request.headers.get("user-agent") or "")[:255],
        remember=body.remember,
    )
    clear_login(ip, scope=email)  # successful login resets failed attempt count
    write_audit(
        user_id=str(user.id),
        username=user.username,
        action="LOGIN",
        resource="auth",
        details=f"Session for {user.email} created",
        request_id=request.headers.get("x-request-id", ""),
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserOut.model_validate(user).model_dump(),
    }


def _check_login_rate_limit(ip: str, email: str) -> None:
    if is_login_rate_limited(ip, scope=email):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please wait and try again.",
        )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/logout")
def logout(
    user: User = Depends(get_current_user),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    token = ""
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token) if token else None
    sid = int(payload["sid"]) if payload and payload.get("sid") else None
    if sid:
        revoke_session(db, sid)
    write_audit(
        user_id=str(user.id),
        username=user.username,
        action="LOGOUT",
        resource="auth",
        details=f"Session {sid} revoked" if sid else "Logout (no session)",
    )
    return {"status": "ok"}