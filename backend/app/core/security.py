"""Core security utilities: password hashing, JWT tokens, RBAC, sessions."""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from ..core.config import settings

PASSWORD_HASH_ITERATIONS = 200_000

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    """Trim, lower-case, and collapse internal whitespace in an email address."""
    if not email:
        return ""
    return re.sub(r"\s+", " ", email.strip()).lower()


def validate_email(email: str) -> bool:
    """Basic format check for a normalized email address."""
    return bool(email) and bool(EMAIL_REGEX.match(email))


def password_strength(password: str) -> list[str]:
    """Return a list of failed password-strength rules (empty if acceptable)."""
    issues = []
    if not password:
        issues.append("Password is required.")
        return issues
    if len(password) < 8:
        issues.append("Password must be at least 8 characters.")
    if not re.search(r"[a-z]", password):
        issues.append("Password must include a lowercase letter.")
    if not re.search(r"[A-Z]", password):
        issues.append("Password must include an uppercase letter.")
    if not re.search(r"\d", password):
        issues.append("Password must include a number.")
    return issues


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-SHA256 and a random salt."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PASSWORD_HASH_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a stored PBKDF2 hash."""
    try:
        algorithm, iterations, salt, expected_hex = hashed.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str,
    role: str,
    username: str,
    session_id: Optional[int] = None,
    remember: bool = False,
) -> str:
    """Create a signed JWT access token."""
    minutes = (
        settings.SESSION_REMEMBER_DAYS * 24 * 60
        if remember
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {
        "sub": subject,
        "role": role,
        "username": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if session_id is not None:
        payload["sid"] = session_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT access token."""
    try:
        return jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except jwt.PyJWTError:
        return None


ROLE_PRIORITY = {
    "VIEWER": 1,
    "ANALYST": 2,
    "MANAGER": 3,
    "ADMIN": 4,
}


def role_at_least(role: str, minimum: str) -> bool:
    """Check if a role has at least the given permission level."""
    return ROLE_PRIORITY.get(role, 0) >= ROLE_PRIORITY.get(minimum, 0)


def is_admin_role(role: str) -> bool:
    return role == "ADMIN"


APPROVAL_REQUIRED_ROLE = "MANAGER"