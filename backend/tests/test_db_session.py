"""
Phase 1 database plumbing tests.

There are no models yet (Phase 2), so these tests only verify that the
engine/session machinery is wired correctly — not that any data can be
persisted, since nothing defines a table yet.
"""

from sqlalchemy import text

from app.db.session import SessionLocal, engine


def test_engine_is_configured():
    assert engine is not None
    assert str(engine.url).startswith("sqlite")


def test_session_can_be_created_and_closed():
    db = SessionLocal()
    try:
        # No tables exist yet — this just proves the connection itself works.
        result = db.execute(text("SELECT 1"))
        assert result.scalar() == 1
    finally:
        db.close()


def test_get_db_dependency_yields_a_working_session():
    from app.db.session import get_db

    gen = get_db()
    db = next(gen)
    try:
        result = db.execute(text("SELECT 1"))
        assert result.scalar() == 1
    finally:
        gen.close()
