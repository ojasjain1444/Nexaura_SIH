"""
bis_crossref.py — Cross-Reference with bis_ingestion SQLite DB

Project: Nexaura (SIH 2026 — SIH26107)

READ-ONLY access to the existing bis_ingestion SQLite database.

Purpose:
    - Enrich KnowledgeUnit metadata with official BIS Portal status
    - Verify standard_number against known BIS catalogue
    - Get official titles, status, amendment info
    - NEVER modify bis_ingestion tables

CRITICAL:
    DO NOT import or modify anything from bis_ingestion/.
    Use only raw SQLite3 queries against the DB file.
    If DB unavailable, fall back gracefully — never raise.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default path to the existing bis_ingestion SQLite DB
DEFAULT_BIS_DB = Path("bis_ingestion") / "data" / "bis_standards.db"


class BISCrossRef:
    """
    Read-only cross-reference against the bis_ingestion SQLite database.

    Enriches document metadata with authoritative BIS Portal data
    without touching or modifying the bis_ingestion module.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """
        Args:
            db_path: Path to the bis_standards.db SQLite file.
                     Defaults to bis_ingestion/data/bis_standards.db.
        """
        self.db_path = Path(db_path) if db_path else DEFAULT_BIS_DB
        self._available = False
        self._check_availability()

    def _check_availability(self) -> None:
        """Check if the SQLite DB is accessible."""
        if self.db_path.exists():
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    conn.execute("SELECT 1")
                self._available = True
                logger.info("BIS cross-reference DB available: %s", self.db_path)
            except Exception as exc:
                logger.warning("BIS DB not usable: %s", exc)
        else:
            logger.info(
                "BIS cross-reference DB not found at %s — enrichment disabled",
                self.db_path,
            )

    @property
    def is_available(self) -> bool:
        """True if the SQLite DB is available and readable."""
        return self._available

    def lookup(self, standard_number: str) -> Optional[dict[str, Any]]:
        """
        Look up a standard number in the BIS catalogue.

        Args:
            standard_number: Normalized IS number, e.g. "IS 456".

        Returns:
            Dict with official metadata, or None if not found / DB unavailable.

        Fields returned (if found):
            standard_number, title, status, edition, year,
            part, amendment, technical_committee
        """
        if not self._available:
            return None

        # Try several normalized forms of the number
        candidates = self._make_search_candidates(standard_number)

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                # Try each candidate
                for candidate in candidates:
                    # Flexible LIKE query — handles "IS 456", "IS456", etc.
                    cur.execute(
                        """
                        SELECT * FROM bis_standards
                        WHERE UPPER(standard_number) LIKE UPPER(?)
                        LIMIT 1
                        """,
                        (f"%{candidate}%",),
                    )
                    row = cur.fetchone()
                    if row:
                        result = dict(row)
                        logger.debug(
                            "Cross-ref match: %s → %s (status=%s)",
                            standard_number,
                            result.get("standard_number"),
                            result.get("status"),
                        )
                        return result

        except Exception as exc:
            logger.warning("Cross-ref lookup failed for %s: %s", standard_number, exc)

        return None

    def enrich_metadata(self, meta) -> None:
        """
        Enrich a DocumentMetadata object with BIS catalogue data.

        Only enriches fields that are currently "unknown" or None.
        NEVER overwrites values already extracted from the document.

        Args:
            meta: DocumentMetadata instance (modified in place).
        """
        if not self._available or not meta.standard_number:
            return

        row = self.lookup(meta.standard_number)
        if not row:
            return

        # Only fill in missing fields — document is authoritative
        if meta.title is None and row.get("title"):
            meta.title = row["title"]
            logger.debug("Enriched title from BIS DB: %s", meta.title[:60])

        if meta.status == "unknown" and row.get("status"):
            meta.status = row["status"]
            logger.debug("Enriched status from BIS DB: %s", meta.status)

        if meta.year is None and row.get("year"):
            try:
                meta.year = int(row["year"])
            except (ValueError, TypeError):
                pass

        if meta.technical_committee is None and row.get("technical_committee"):
            meta.technical_committee = row["technical_committee"]

    def get_all_standard_numbers(self) -> list[str]:
        """
        Get all standard numbers from the BIS catalogue.

        Returns:
            List of standard number strings (empty if DB unavailable).
        """
        if not self._available:
            return []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cur = conn.cursor()
                cur.execute("SELECT standard_number FROM bis_standards ORDER BY standard_number")
                return [row[0] for row in cur.fetchall() if row[0]]
        except Exception as exc:
            logger.warning("Failed to list standard numbers: %s", exc)
            return []

    def get_amendments(self, standard_number: str) -> list[dict]:
        """
        Get amendment records for a standard.

        Args:
            standard_number: IS standard number.

        Returns:
            List of amendment dicts (empty if none found).
        """
        if not self._available:
            return []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT * FROM bis_amendments
                    WHERE UPPER(standard_number) LIKE UPPER(?)
                    """,
                    (f"%{standard_number}%",),
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception:
            return []

    def _make_search_candidates(self, standard_number: str) -> list[str]:
        """Generate multiple search forms for a standard number."""
        import re
        candidates = [standard_number]
        # Strip spaces: "IS 456" → "IS456"
        no_space = standard_number.replace(" ", "")
        if no_space != standard_number:
            candidates.append(no_space)
        # Extract just the numeric part: "IS 456" → "456"
        nums = re.findall(r"\d+", standard_number)
        if nums:
            candidates.append(nums[0])
        return candidates
