"""End-to-end acceptance check run OUTSIDE pytest (a real server-like process)
to prove the simplified auth flow works in production conditions."""

import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.gettempdir()) / "nexus_flow_check.db"
if TMP.exists():
    TMP.unlink()

os.environ["DATABASE_URL"] = "sqlite:///" + str(TMP).replace("\\", "/")
os.environ["DEMO_MODE"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["NEXUS_PORT"] = "8011"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as c:
    # 1. Register -> 200 with access_token + user (auto-login).
    r = c.post("/api/auth/register", json={
        "email": "VERIFY.User@Example.com ",
        "username": "verifyuser",
        "full_name": "Verify User",
        "password": "Str0ngPass1!",
        "confirm_password": "Str0ngPass1!",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["access_token"]
    assert body["user"]["email"] == "verify.user@example.com", body["user"]
    assert "email_verified" not in body["user"]
    token = body["access_token"]
    print("register -> 200 auto-login token issued, no email_verified field")

    # 2. Token is immediately valid.
    me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "verify.user@example.com"
    print("me -> 200 with register token (auto-authenticated)")

    # 3. Logout revokes; token dead afterwards.
    assert c.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    print("logout -> 200, then me -> 401 (revoked)")

    # 4. Login with same credentials works immediately.
    lg = c.post("/api/auth/login", json={"email": "verify.user@example.com", "password": "Str0ngPass1!"})
    assert lg.status_code == 200, lg.text
    assert lg.json()["token_type"] == "bearer"
    assert "email_verified" not in lg.json()["user"]
    print("login -> 200 (no verification required)")

    # 5. Wrong password -> 401.
    assert c.post("/api/auth/login", json={"email": "verify.user@example.com", "password": "BadPass9!"}).status_code == 401
    print("wrong password -> 401")

    # 6. Duplicate email -> 409, still exactly one user row.
    dup = c.post("/api/auth/register", json={
        "email": "verify.user@example.com", "username": "verifyuser2",
        "full_name": "Dup", "password": "Str0ngPass1!", "confirm_password": "Str0ngPass1!",
    })
    assert dup.status_code == 409, dup.text
    from app.models import User
    from app.database.session import SessionLocal
    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == "verify.user@example.com").count() == 1
        row = db.query(User).filter(User.email == "verify.user@example.com").first()
        assert row.hashed_password.startswith("pbkdf2_sha256$")
        assert row.hashed_password != "Str0ngPass1!"
    finally:
        db.close()
    print("duplicate register -> 409, single row, password hashed")

    # 7. Verification / forgot endpoints are gone (404 or SPA catch-all 405).
    for path in ("verify-otp", "resend-otp", "forgot-password", "reset-password"):
        res = c.post(f"/api/auth/{path}", json={"email": "x@nx.io", "otp": "000000", "purpose": "verify"})
        assert res.status_code in (404, 405), (path, res.status_code)
    print("verify-otp / resend-otp / forgot-password / reset-password -> removed (404/405)")

    # 8. Schema: no otp_verifications, no email_verified anywhere.
    from sqlalchemy import inspect
    from app.database.session import engine
    insp = inspect(engine)
    assert "otp_verifications" not in insp.get_table_names()
    assert "email_verified" not in {c["name"] for c in insp.get_columns("users")}
    print("schema clean: no otp_verifications, no users.email_verified")

engine.dispose()
TMP.unlink(missing_ok=True)
print("E2E SIMPLIFIED AUTH CHECK PASSED")