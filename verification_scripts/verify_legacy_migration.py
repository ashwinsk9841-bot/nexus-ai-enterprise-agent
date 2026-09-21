"""Verify legacy-DB migration: an old DB that still has users.email_verified
and otp_verifications must keep its users but drop the verification schema.
Runs as a real (non-pytest) process against a scratch SQLite file."""

import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.gettempdir()) / "nexus_migrate_check.db"
if TMP.exists():
    TMP.unlink()

os.environ["DATABASE_URL"] = "sqlite:///" + str(TMP).replace("\\", "/")
os.environ["DEMO_MODE"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["NEXUS_PORT"] = "8011"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import sqlite3
from app.core.security import hash_password
from app.main import init_db


def legacy_conn():
    return sqlite3.connect(str(TMP))


# 1. Build a LEGACY schema: users WITH email_verified, plus otp_verifications.
conn = legacy_conn()
conn.executescript(
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email VARCHAR(255) NOT NULL UNIQUE,
        username VARCHAR(64) NOT NULL UNIQUE,
        full_name VARCHAR(255) DEFAULT '',
        hashed_password VARCHAR(256) NOT NULL,
        role VARCHAR(32) DEFAULT 'VIEWER',
        is_active BOOLEAN DEFAULT 1,
        demo_account BOOLEAN DEFAULT 0,
        email_verified BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_login DATETIME
    );
    CREATE TABLE otp_verifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        email VARCHAR(255),
        purpose VARCHAR(32),
        otp_hash VARCHAR(128),
        attempts INTEGER DEFAULT 0,
        used BOOLEAN DEFAULT 0,
        expires_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    INSERT INTO otp_verifications (email, purpose, otp_hash) VALUES ('olduser@nexus.io', 'verify', 'x');
    INSERT INTO users (email, username, full_name, hashed_password, role, email_verified)
        VALUES ('olduser@nexus.io', 'olduser', 'Old User', %s, 'ADMIN', 1);
    """
    % ("'old-hash'" if False else "'abc'"),
)
conn.commit()
conn.close()
print("[1] legacy DB built with email_verified=1 and otp_verifications row")

# 2. Run the app migration the same way startup does.
init_db()
print("[2] init_db() ran")

# 3. Verify migration result.
conn = legacy_conn()
users = conn.execute("SELECT * FROM users").fetchall()
try:
    otp_count = conn.execute("SELECT COUNT(*) FROM otp_verifications").fetchone()[0]
    otp_still_there = True
except sqlite3.OperationalError:
    otp_count, otp_still_there = 0, False
cols = [c[1] for c in conn.execute("PRAGMA table_info(users)").fetchall()]
conn.close()

assert users, "user rows must be preserved"
email = [r for r in users if r[1] == "olduser@nexus.io"]
assert email, "legacy user must still exist"
assert "email_verified" not in cols, f"users.email_verified still present: {cols}"
assert not otp_still_there, "otp_verifications table still present"
print("[3] OK: users preserved, users.email_verified dropped, otp_verifications dropped")

# 4. Confirm the app model agrees with the migrated schema.
from sqlalchemy import inspect
from app.database.session import engine

insp = inspect(engine)
assert "otp_verifications" not in insp.get_table_names()
assert "email_verified" not in {c["name"] for c in insp.get_columns("users")}
print("[4] OK: SQLAlchemy models match migrated schema (no email_verified / otp_verifications)")

engine.dispose()
TMP.unlink(missing_ok=True)
print("LEGACY MIGRATION CHECK PASSED")