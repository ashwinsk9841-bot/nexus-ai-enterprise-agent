"""Simplified authentication acceptance tests.

The legacy email-verification / OTP / forgot-password flow was removed:
registration must sign a user straight in and login must be immediate.
This suite verifies the whole post-simplification contract.
"""

import pytest

from app.database.session import SessionLocal
from tests.conftest import auth


def _register(client, email="simp.user@nexus.io", username="simpuser", password="Str0ngPass1!"):
    return client.post(
        "/api/auth/register",
        json={
            "email": email,
            "username": username,
            "full_name": "Simp User",
            "password": password,
            "confirm_password": password,
        },
    )


def _user_row(email):
    from app.models import User

    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == email).first()
    finally:
        db.close()


# ---- registration ----------------------------------------------------------

def test_register_stores_user_in_db(client):
    email = "simp.store@nexus.io"
    res = _register(client, email=email, username="simpstore")
    assert res.status_code == 200, res.text
    row = _user_row(email)
    assert row is not None
    assert row.username == "simpstore"
    assert row.role == "VIEWER"
    assert row.is_active is True


def test_register_hashes_password_not_plaintext(client):
    email = "simp.hash@nexus.io"
    res = _register(client, email=email, username="simphash", password="Str0ngPass1!")
    assert res.status_code == 200
    row = _user_row(email)
    assert row is not None
    assert row.hashed_password != "Str0ngPass1!"
    assert row.hashed_password.startswith("pbkdf2_sha256$")


def test_register_normalizes_email(client):
    email = "  Simp.Case@Nexus.io "
    res = _register(client, email=email, username="simpcase")
    assert res.status_code == 200, res.text
    assert _user_row("simp.case@nexus.io") is not None
    assert _user_row("Simp.Case@nexus.io") is None


def test_duplicate_email_rejected(client):
    email = "simp.dup@nexus.io"
    assert _register(client, email=email, username="simpdup1").status_code == 200
    res = _register(client, email=email, username="simpdup2")
    assert res.status_code == 409
    assert _user_row(email) is not None  # original still present, no duplicate
    from app.models import User

    db = SessionLocal()
    try:
        count = db.query(User).filter(User.email == email).count()
    finally:
        db.close()
    assert count == 1


def test_register_invalid_password_rejected(client):
    res = _register(client, email="simp.weak@nexus.io", username="simpweak", password="short")
    assert res.status_code == 400
    assert _user_row("simp.weak@nexus.io") is None


# ---- auto-login on registration -------------------------------------------

def test_register_auto_logs_in(client):
    email = "simp.autologin@nexus.io"
    res = _register(client, email=email, username="simpauto")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["access_token"]
    assert body["user"]["email"] == email
    assert body["user"]["role"] == "VIEWER"
    # the returned token is immediately valid
    me = client.get("/api/auth/me", headers=auth(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == email


def test_register_response_has_no_verification_fields(client):
    body = _register(client).json()
    assert "email_verified" not in body["user"]
    assert "pending_verification" not in body


# ---- login ----------------------------------------------------------------

def test_login_same_credentials_works(client):
    email = "simp.login@nexus.io"
    password = "Str0ngPass1!"
    assert _register(client, email=email, username="simplogin", password=password).status_code == 200
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    assert res.json()["token_type"] == "bearer"
    assert "email_verified" not in res.json()["user"]


def test_login_wrong_password_fails(client):
    email = "simp.wrongpw@nexus.io"
    assert _register(client, email=email, username="simpwrongpw").status_code == 200
    res = client.post("/api/auth/login", json={"email": email, "password": "WrongPass9!"})
    assert res.status_code == 401


def test_logout_then_me_401(client):
    email = "simp.logout@nexus.io"
    reg = _register(client, email=email, username="simplogout")
    token = reg.json()["access_token"]
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 200
    assert client.post("/api/auth/logout", headers=auth(token)).status_code == 200
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401


# ---- verification / forgot-password endpoints removed ----------------------

@pytest.mark.parametrize(
    "path",
    [
        ("/api/auth/verify-otp"),
        ("/api/auth/resend-otp"),
        ("/api/auth/forgot-password"),
        ("/api/auth/reset-password"),
    ],
)
def test_verification_endpoints_removed(client, path):
    res = client.post(path, json={"email": "x@nexus.io", "otp": "000000", "purpose": "verify"})
    # 404 = not defined; 405 = only the SPA GET catch-all matches the path.
    # Either way the old POST handler is gone.
    assert res.status_code in (404, 405)


def test_auth_config_has_no_verification_mode(client):
    body = client.get("/api/auth/config").json()
    assert "email_mode" not in body
    assert "require_email_verification" not in body
    assert "otp" not in body


# ---- schema no longer contains verification columns ------------------------

def test_schema_has_no_verification_tables_or_columns(client):
    from sqlalchemy import inspect

    from app.database.session import engine

    insp = inspect(engine)
    assert "otp_verifications" not in insp.get_table_names()
    col_names = {c["name"] for c in insp.get_columns("users")}
    assert "email_verified" not in col_names