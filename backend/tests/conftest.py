"""
Shared test fixtures.

Every test that touches the database uses a fresh, isolated SQLite file
per test (created in a temp directory, deleted afterward) — never the
developer's real bis_sahayak.db. The FastAPI app's `get_db` dependency is
overridden to point at this isolated database for the duration of each
test.
"""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import get_db
import app.models  # noqa: F401 — ensure all models are registered on Base.metadata


def create_all_tables(engine) -> None:
    """Creates every ORM-mapped table plus the hand-written FTS5 virtual
    table (document_chunks_fts — see app/rag/keyword_search.py and the
    Phase 10 migration), so a test database always matches what a real,
    fully-migrated database has. Base.metadata.create_all() alone only
    creates ORM-mapped tables; FTS5 virtual tables have no ORM
    representation. Shared by every test module that builds its own engine
    directly rather than using the test_db_engine fixture below."""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE VIRTUAL TABLE document_chunks_fts USING fts5(chunk_id UNINDEXED, document_id UNINDEXED, text)"
        )


@pytest.fixture()
def test_db_engine(tmp_path: Path):
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    create_all_tables(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(test_db_engine):
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(test_db_engine):
    from app.main import app

    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def isolated_storage(tmp_path, monkeypatch):
    """Redirects app.core.config.get_settings().storage_path to a temp
    directory for the duration of a test, so document ingestion tests never
    write files into the real backend/data/processed/."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path / "storage"))
    yield tmp_path / "storage"
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolated_llm_settings(monkeypatch):
    """Ensures no test's behavior depends on whatever LLM provider a
    developer happens to have configured in their own local backend/.env
    (e.g. LLM_PROVIDER=ollama for local manual testing — see
    docs/CHAT_RAG.md). Settings.model_config reads backend/.env directly
    (env_file=".env" — see app/core/config.py), independent of the process
    environment, so merely deleting an already-unset OS env var would not
    override a value present in that file; setting each var to an EMPTY
    STRING via monkeypatch.setenv does override it (real OS env vars take
    precedence over .env file values in pydantic-settings), and
    get_llm_provider()'s own `if not provider_name` check already treats
    an empty string the same as unset. Every test starts with
    LLM_PROVIDER/LLM_API_KEY/LLM_MODEL/OLLAMA_BASE_URL cleared this way by
    default, matching the "no provider configured" baseline most tests
    assume; a test that specifically wants a provider configured sets it
    itself via monkeypatch.setenv or by passing an explicit llm_provider to
    ChatService."""
    from app.core.config import get_settings

    for var in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.setenv(var, "")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")  # restore the documented default
    # Same reasoning as the LLM settings above: this must never depend on
    # a developer's own .env, since it gates a real, live network call
    # (app/product/external_standard_fallback.py) that would otherwise
    # make the test suite flaky/slow/network-dependent. Confirmed
    # necessary the hard way — an early version of this fallback had no
    # such gate and hung the entire test suite by actually calling
    # Internet Archive from a product-discovery test with no local
    # candidates.
    monkeypatch.setenv("EXTERNAL_STANDARD_FALLBACK_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
