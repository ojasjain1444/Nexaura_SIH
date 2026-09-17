"""
crossref_connector.py — Read-only Connector to bis_ingestion Data

Project: Nexaura (SIH 2026 — SIH26107)

Discovers standards, amendments, laboratories, and manuals from existing
bis_ingestion SQLite/CSV databases safely without touching bis_ingestion code.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from nexaura.backend.acquisition.document_models import DocumentMetadata, DocumentType, AccessStatus

logger = logging.getLogger(__name__)


class BISIngestionConnector:
    """
    Read-only discovery connector to bis_ingestion/data/ SQLite database.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            # Auto-discover bis_ingestion DB relative to project root
            root = Path(__file__).resolve().parent.parent.parent.parent
            db_path = root / "bis_ingestion" / "data" / "bis_standards.db"
        self.db_path = Path(db_path)

    def is_available(self) -> bool:
        """Check if bis_ingestion SQLite database exists."""
        return self.db_path.exists() and self.db_path.is_file()

    def discover_all_records(self) -> List[Dict[str, Any]]:
        """Fetch all standards metadata records from SQLite if present."""
        if not self.is_available():
            logger.info("bis_ingestion SQLite database not found at %s", self.db_path)
            return []

        records = []
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Inspect available tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]

            if "standards" in tables:
                cursor.execute("SELECT * FROM standards LIMIT 1000;")
                records = [dict(row) for row in cursor.fetchall()]
            elif "bis_metadata" in tables:
                cursor.execute("SELECT * FROM bis_metadata LIMIT 1000;")
                records = [dict(row) for row in cursor.fetchall()]

            conn.close()
            logger.info("Discovered %d metadata records from bis_ingestion SQLite", len(records))
        except Exception as exc:
            logger.warning("Failed to read bis_ingestion SQLite database: %s", exc)

        return records
