import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from ..core.config import settings

# Serverless (Vercel): many short-lived instances must not exhaust the
# Postgres connection limit, so keep each instance's pool tiny.
_SERVERLESS = bool(os.environ.get("VERCEL"))

_ENGINE_KW = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}
if _SERVERLESS:
    _ENGINE_KW.update(pool_size=2, max_overflow=2)
else:
    _ENGINE_KW.update(pool_size=10, max_overflow=20)

engine = create_engine(settings.DATABASE_URL, **_ENGINE_KW)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
