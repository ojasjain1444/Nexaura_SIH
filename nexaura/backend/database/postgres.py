"""
postgres.py — PostgreSQL Connection and Schema Initialization

Project: Nexaura (SIH 2026 — SIH26107)

Provides:
    - Connection pool management
    - Schema initialization
    - Connection context manager

Connection URL from POSTGRES_URL environment variable.
Never hardcoded.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator, Optional

logger = logging.getLogger(__name__)


def get_connection_url() -> str:
    """
    Get PostgreSQL connection URL from environment.
    Never hardcoded — always from POSTGRES_URL env var.
    """
    url = os.environ.get("POSTGRES_URL", "")
    if not url:
        raise ValueError(
            "POSTGRES_URL environment variable must be set. "
            "Example: postgresql://postgres:password@localhost:5432/nexaura_bis"
        )
    return url


class PostgreSQLManager:
    """
    PostgreSQL connection and schema manager.

    Usage:
        manager = PostgreSQLManager()
        manager.init_schema()

        with manager.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM clauses")
    """

    def __init__(self, url: Optional[str] = None) -> None:
        self.url = url or get_connection_url()
        self._pool = None

    def init_schema(self) -> None:
        """
        Create all tables if they don't exist.
        Safe to run multiple times (idempotent).
        """
        from nexaura.backend.database.schema import get_schema_ddl
        try:
            import psycopg2
        except ImportError as e:
            raise ImportError("psycopg2-binary required: pip install psycopg2-binary") from e

        logger.info("Initializing PostgreSQL schema...")
        with self._get_raw_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(get_schema_ddl())
            conn.commit()
        logger.info("PostgreSQL schema initialized successfully.")

    @contextmanager
    def connection(self):
        """Context manager for a PostgreSQL connection."""
        conn = self._get_raw_connection()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def test_connection(self) -> bool:
        """Test database connectivity."""
        try:
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            logger.info("PostgreSQL connection OK")
            return True
        except Exception as exc:
            logger.error("PostgreSQL connection failed: %s", exc)
            return False

    def _get_raw_connection(self):
        """Get a raw psycopg2 connection."""
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(self.url)
        return conn


# Singleton instance (initialized lazily)
_manager: Optional[PostgreSQLManager] = None


def get_manager() -> PostgreSQLManager:
    """Get or create the global PostgreSQL manager."""
    global _manager
    if _manager is None:
        _manager = PostgreSQLManager()
    return _manager
