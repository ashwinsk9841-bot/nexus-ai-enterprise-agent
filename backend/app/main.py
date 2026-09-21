"""FastAPI application entry point for NEXUS."""

import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from .core.config import settings
from .database.session import Base, engine, SessionLocal
from .models import User
from .services.demo_data import seed_demo_data
from .core.security import hash_password

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("nexus")


def _sqlite_alter_if_missing(db, table: str, column: str, coltype: str):
    """Idempotent ALTER TABLE ADD COLUMN for SQLite (no-op if column exists)."""
    try:
        with engine.connect() as conn:
            cols = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            existing = {c[1] for c in cols}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
                conn.commit()
                logger.info("Migrated %s.%s (added %s %s)", table, column, column, coltype)
    except Exception:
        pass  # PostgreSQL / other engines: create_all handles it


def _sqlite_drop_column_if_present(table: str, column: str):
    """Idempotent ALTER TABLE DROP COLUMN for SQLite (no-op if column absent)."""
    try:
        with engine.connect() as conn:
            cols = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            existing = {c[1] for c in cols}
            if column in existing:
                conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
                conn.commit()
                logger.info("Migrated %s.%s (dropped column %s)", table, column, column)
    except Exception:
        pass


def _drop_otp_schema():
    """Remove verification-only schema (otp_verifications table + users.email_verified).

    Safe on any engine: every statement is defensive and failures are ignored
    (e.g. a column/table that already left, or an engine without DROP COLUMN).
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS otp_verifications"))
            conn.commit()
            logger.info("Removed otp_verifications table")
    except Exception:
        pass
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS email_verified"))
            conn.commit()
            logger.info("Removed users.email_verified column")
    except Exception:
        pass


def _run_migrations():
    """Idempotent schema migrations for existing SQLite databases."""
    if "sqlite" not in settings.DATABASE_URL:
        return
    _sqlite_alter_if_missing(db=None, table="users", column="organization", coltype="VARCHAR(255) DEFAULT ''")
    _sqlite_alter_if_missing(db=None, table="users", column="must_change_password", coltype="BOOLEAN DEFAULT 0")
    _sqlite_alter_if_missing(db=None, table="audit_logs", column="request_id", coltype="VARCHAR(64) DEFAULT ''")
    _sqlite_alter_if_missing(db=None, table="audit_logs", column="result", coltype="VARCHAR(32) DEFAULT 'SUCCESS'")
    _sqlite_drop_column_if_present(table="users", column="email_verified")


def init_db():
    """Create tables, seed demo users/data, and run startup migrations."""
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    _drop_otp_schema()
    with SessionLocal() as db:
        if db.query(User).count() == 0:
            demo_users = [
                {
                    "email": "demo@nexus.io",
                    "username": "demo",
                    "full_name": "Demo Admin",
                    "password": "demo1234",
                    "role": "ADMIN",
                },
                {
                    "email": "manager@nexus.io",
                    "username": "manager",
                    "full_name": "Morgan Reyes",
                    "password": "manager123",
                    "role": "MANAGER",
                },
                {
                    "email": "analyst@nexus.io",
                    "username": "analyst",
                    "full_name": "Ava Chen",
                    "password": "analyst123",
                    "role": "ANALYST",
                },
                {
                    "email": "viewer@nexus.io",
                    "username": "viewer",
                    "full_name": "Viewer Account",
                    "password": "viewer123",
                    "role": "VIEWER",
                },
            ]
            for u in demo_users:
                db.add(
                    User(
                        email=u["email"],
                        username=u["username"],
                        full_name=u["full_name"],
                        hashed_password=hash_password(u["password"]),
                        role=u["role"],
                        demo_account=True,
                        is_active=True,
                    )
                )
            db.commit()

        # Bootstrap admin from env if configured
        if settings.NEXUS_ADMIN_EMAIL:
            from .core.security import normalize_email
            admin_email = normalize_email(settings.NEXUS_ADMIN_EMAIL)
            existing = db.query(User).filter(User.email == admin_email).first()
            if not existing:
                pw_hash = settings.NEXUS_ADMIN_PASSWORD_HASH or hash_password("admin1234")
                db.add(
                    User(
                        email=admin_email,
                        username=admin_email.split("@")[0],
                        full_name="Admin",
                        hashed_password=pw_hash,
                        role="ADMIN",
                        is_active=True,
                    )
                )
                db.commit()
                logger.info("Bootstrapped admin user: %s", admin_email)

        if settings.DEMO_MODE:
            try:
                seed_demo_data(db)
            except Exception:
                logger.exception("Demo data seeding failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("NEXUS starting up (env=%s, demo=%s)", settings.ENVIRONMENT, settings.DEMO_MODE)
    try:
        init_db()
    except Exception:
        logger.exception("Database initialization failed — check DATABASE_URL and that Postgres is running")
    yield
    logger.info("NEXUS shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise AI Intelligence & Operations Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request timing + error envelope
@app.middleware("http")
async def add_timing(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    if "/api/" in request.url.path:
        response.headers["X-Nexus-Timing-Ms"] = str(int((time.time() - start) * 1000))
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


# --- Routers ---
from .api.auth import router as auth_router
from .api.dashboard import router as dashboard_router
from .api.agents import router as agents_router
from .api.analytics import router as analytics_router
from .api.security import router as security_router
from .api.operations import router as operations_router
from .api.incidents import router as incidents_router
from .api.knowledge import router as knowledge_router
from .api.reports import router as reports_router
from .api.ai import router as ai_router
from .api.approvals import router as approvals_router
from .api.notifications import router as notifications_router
from .api.admin import router as admin_router

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(agents_router, prefix="/api/agents", tags=["Agents"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(security_router, prefix="/api/security", tags=["Security"])
app.include_router(operations_router, prefix="/api/operations", tags=["Operations"])
app.include_router(incidents_router, prefix="/api/incidents", tags=["Incidents"])
app.include_router(knowledge_router, prefix="/api/knowledge", tags=["Knowledge"])
app.include_router(reports_router, prefix="/api/reports", tags=["Reports"])
app.include_router(ai_router, prefix="/api/ai", tags=["AI"])
app.include_router(approvals_router, prefix="/api/approvals", tags=["Approvals"])
app.include_router(notifications_router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])


@app.get("/api/health", tags=["Health"])
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "demo_mode": settings.DEMO_MODE,
        "ai_configured": bool(settings.OPENAI_API_KEY),
    }


@app.get("/api/system/status", tags=["System"])
def system_status():
    """Status used by the frontend system pill."""
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "system": "Operational" if db_ok else "Degraded",
        "database": "HEALTHY" if db_ok else "UNREACHABLE",
        "ai": "CONFIGURED" if settings.OPENAI_API_KEY else "DEMO",
        "demo_mode": settings.DEMO_MODE,
    }


# --- Frontend serving (single website) ----------------------------------------

def mount_frontend(target_app: FastAPI) -> None:
    """Serve the built frontend (dist/) from the same FastAPI process.

    The backend is the ONE server: API lives under /api/..., everything else is
    the SPA. Unknown non-API paths fall back to index.html so direct page
    refreshes (and any deep link) still load the app shell.
    """
    import os
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]  # <repo>/
    frontend_dir = project_root / "frontend"
    dist_dir = frontend_dir / "dist"
    static_root = str(
        dist_dir.resolve() if (dist_dir / "index.html").is_file() else frontend_dir.resolve()
    )

    def safe_join(rel: str) -> str:
        base = static_root
        rel = rel.replace("\\", "/").lstrip("/")
        target = os.path.realpath(os.path.join(base, rel))
        if target != base and not target.startswith(base + os.sep):
            raise HTTPException(status_code=404, detail="Not found")
        return target

    def index_response():
        return FileResponse(os.path.join(static_root, "index.html"))

    @target_app.get("/", include_in_schema=False)
    def serve_index():
        return index_response()

    @target_app.get("/{full_path:path}", include_in_schema=False)
    def serve_static(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        target = safe_join(full_path)
        if os.path.isdir(target):
            target = os.path.join(target, "index.html")
        if os.path.isfile(target):
            return FileResponse(target)
        return index_response()


mount_frontend(app)