"""
Database engine and session factory.

Phase 1 scope: this creates the SQLAlchemy engine/session machinery so
Phase 2 can start persisting real data without re-plumbing this layer.
Nothing in Phase 1 calls `get_db()` — no route in this phase touches the
database. The engine is created lazily and does not need a live database
to import this module or start the app (SQLite creates its file on first
use; a misconfigured PostgreSQL URL would only fail on first actual query,
not at import/startup time).
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session. Not used by any
    route yet in Phase 1 — provided for Phase 2."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
