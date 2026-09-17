"""
storage/db.py — SQLite persistence layer for BIS Standards pipeline.

Uses Python's built-in sqlite3 — zero external dependencies.
All writes are idempotent (INSERT OR REPLACE) keyed on standard_number + source_system.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Iterator, Optional

from bis_ingestion.config import SQLITE_DB_PATH
from bis_ingestion.schemas import BISLab, BISStandard

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_DDL_STANDARDS = """
CREATE TABLE IF NOT EXISTS bis_standards (
    id                      TEXT PRIMARY KEY,
    standard_number         TEXT NOT NULL,
    doc_no                  TEXT,
    part                    TEXT,
    section                 TEXT,
    edition_year            TEXT,
    title                   TEXT,
    scope                   TEXT,
    status                  TEXT,
    publication_date        TEXT,
    reaffirmation_date      TEXT,
    withdrawal_date         TEXT,
    amendments              TEXT,       -- JSON array
    supersedes              TEXT,
    superseded_by           TEXT,
    related_standards       TEXT,       -- JSON array
    ics_code                TEXT,
    technical_committee     TEXT,
    department              TEXT,
    product_category        TEXT,
    certification_scheme    TEXT,
    testing_information     TEXT,
    has_mandatory_certification INTEGER, -- 0/1/NULL
    labs                    TEXT,       -- JSON array
    source_url              TEXT NOT NULL,
    document_url            TEXT,
    amendment_urls          TEXT,       -- JSON array
    source_system           TEXT NOT NULL DEFAULT 'BIS',
    last_checked            TEXT,
    crawl_timestamp         TEXT,
    UNIQUE(standard_number, source_system)
);
"""

_DDL_LABS = """
CREATE TABLE IF NOT EXISTS bis_labs (
    id              TEXT PRIMARY KEY,
    lab_name        TEXT NOT NULL,
    osl_code        TEXT,
    is_number       TEXT NOT NULL,
    is_doc_no       TEXT,
    is_part         TEXT,
    is_section      TEXT,
    is_year         TEXT,
    product         TEXT,
    grade_type      TEXT,
    testing_charges TEXT,
    validity_date   TEXT,
    remark          TEXT,
    state           TEXT,
    district        TEXT,
    source_url      TEXT NOT NULL,
    last_checked    TEXT,
    crawl_timestamp TEXT,
    UNIQUE(lab_name, is_number)
);
"""

_DDL_CRAWL_LOG = """
CREATE TABLE IF NOT EXISTS crawl_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at          TEXT NOT NULL,
    source          TEXT,
    records_added   INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    errors          INTEGER DEFAULT 0,
    notes           TEXT
);
"""

_DDL_INDICES = [
    "CREATE INDEX IF NOT EXISTS idx_std_number ON bis_standards(standard_number);",
    "CREATE INDEX IF NOT EXISTS idx_std_status  ON bis_standards(status);",
    "CREATE INDEX IF NOT EXISTS idx_std_tc      ON bis_standards(technical_committee);",
    "CREATE INDEX IF NOT EXISTS idx_lab_is      ON bis_labs(is_doc_no);",
    "CREATE INDEX IF NOT EXISTS idx_lab_name    ON bis_labs(lab_name);",
]


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def _connect(db_path: Path = SQLITE_DB_PATH) -> sqlite3.Connection:
    """Open (or create) the SQLite database and return a connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")  # wait up to 30s if DB is locked
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# ---------------------------------------------------------------------------
# Database manager
# ---------------------------------------------------------------------------

class BISDatabase:
    """
    Thin wrapper around SQLite for BIS standards and lab data.

    Usage::

        with BISDatabase() as db:
            db.upsert_standard(standard)
            labs = db.get_labs_for_standard("456")
    """

    def __init__(self, db_path: Path = SQLITE_DB_PATH):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # --- context manager -------------------------------------------------------

    def __enter__(self) -> "BISDatabase":
        self._conn = _connect(self.db_path)
        self._init_schema()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._conn:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("BISDatabase used outside of context manager")
        return self._conn

    # --- schema ----------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create tables and indices if they do not exist."""
        self.conn.execute(_DDL_STANDARDS)
        self.conn.execute(_DDL_LABS)
        self.conn.execute(_DDL_CRAWL_LOG)
        for idx in _DDL_INDICES:
            self.conn.execute(idx)
        self.conn.commit()
        logger.debug("Schema initialised at %s", self.db_path)

    # --- standards -------------------------------------------------------------

    def upsert_standard(self, std: BISStandard) -> None:
        """Insert or replace a BISStandard record."""
        self.conn.execute(
            """
            INSERT INTO bis_standards (
                id, standard_number, doc_no, part, section, edition_year,
                title, scope, status, publication_date, reaffirmation_date,
                withdrawal_date, amendments, supersedes, superseded_by,
                related_standards, ics_code, technical_committee, department,
                product_category, certification_scheme, testing_information,
                has_mandatory_certification, labs, source_url, document_url,
                amendment_urls, source_system, last_checked, crawl_timestamp
            ) VALUES (
                :id, :standard_number, :doc_no, :part, :section, :edition_year,
                :title, :scope, :status, :publication_date, :reaffirmation_date,
                :withdrawal_date, :amendments, :supersedes, :superseded_by,
                :related_standards, :ics_code, :technical_committee, :department,
                :product_category, :certification_scheme, :testing_information,
                :has_mandatory_certification, :labs, :source_url, :document_url,
                :amendment_urls, :source_system, :last_checked, :crawl_timestamp
            )
            ON CONFLICT(standard_number, source_system) DO UPDATE SET
                title                       = excluded.title,
                scope                       = excluded.scope,
                status                      = excluded.status,
                edition_year                = excluded.edition_year,
                publication_date            = excluded.publication_date,
                reaffirmation_date          = excluded.reaffirmation_date,
                withdrawal_date             = excluded.withdrawal_date,
                amendments                  = excluded.amendments,
                supersedes                  = excluded.supersedes,
                superseded_by               = excluded.superseded_by,
                related_standards           = excluded.related_standards,
                ics_code                    = excluded.ics_code,
                technical_committee         = excluded.technical_committee,
                department                  = excluded.department,
                product_category            = excluded.product_category,
                certification_scheme        = excluded.certification_scheme,
                testing_information         = excluded.testing_information,
                has_mandatory_certification = excluded.has_mandatory_certification,
                labs                        = excluded.labs,
                document_url                = excluded.document_url,
                amendment_urls              = excluded.amendment_urls,
                last_checked                = excluded.last_checked,
                crawl_timestamp             = excluded.crawl_timestamp
            """,
            {
                "id": std.id,
                "standard_number": std.standard_number,
                "doc_no": std.doc_no,
                "part": std.part,
                "section": std.section,
                "edition_year": std.edition_year,
                "title": std.title,
                "scope": std.scope,
                "status": std.status,
                "publication_date": std.publication_date,
                "reaffirmation_date": std.reaffirmation_date,
                "withdrawal_date": std.withdrawal_date,
                "amendments": json.dumps(std.amendments),
                "supersedes": std.supersedes,
                "superseded_by": std.superseded_by,
                "related_standards": json.dumps(std.related_standards),
                "ics_code": std.ics_code,
                "technical_committee": std.technical_committee,
                "department": std.department,
                "product_category": std.product_category,
                "certification_scheme": std.certification_scheme,
                "testing_information": std.testing_information,
                "has_mandatory_certification": (
                    int(std.has_mandatory_certification)
                    if std.has_mandatory_certification is not None
                    else None
                ),
                "labs": json.dumps(std.labs),
                "source_url": std.source_url,
                "document_url": std.document_url,
                "amendment_urls": json.dumps(std.amendment_urls),
                "source_system": std.source_system,
                "last_checked": std.last_checked,
                "crawl_timestamp": std.crawl_timestamp,
            },
        )

    def upsert_standards_batch(self, standards: list[BISStandard]) -> int:
        """Bulk upsert. Returns number of records written."""
        for std in standards:
            self.upsert_standard(std)
        self.conn.commit()
        logger.info("Upserted %d standards to DB", len(standards))
        return len(standards)

    def get_standard(self, standard_number: str) -> Optional[dict]:
        """Fetch a single standard by standard_number."""
        cur = self.conn.execute(
            "SELECT * FROM bis_standards WHERE standard_number = ? ORDER BY crawl_timestamp DESC LIMIT 1",
            (standard_number.strip().upper(),),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def iter_all_standards(self) -> Iterator[dict]:
        """Yield all standard records as dicts."""
        cur = self.conn.execute("SELECT * FROM bis_standards ORDER BY standard_number")
        for row in cur:
            yield dict(row)

    def count_standards(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM bis_standards")
        return cur.fetchone()[0]

    # --- labs ------------------------------------------------------------------

    def upsert_lab(self, lab: BISLab) -> None:
        """Insert or replace a BISLab record."""
        self.conn.execute(
            """
            INSERT INTO bis_labs (
                id, lab_name, osl_code, is_number, is_doc_no, is_part,
                is_section, is_year, product, grade_type, testing_charges,
                validity_date, remark, state, district, source_url,
                last_checked, crawl_timestamp
            ) VALUES (
                :id, :lab_name, :osl_code, :is_number, :is_doc_no, :is_part,
                :is_section, :is_year, :product, :grade_type, :testing_charges,
                :validity_date, :remark, :state, :district, :source_url,
                :last_checked, :crawl_timestamp
            )
            ON CONFLICT(lab_name, is_number) DO UPDATE SET
                osl_code        = excluded.osl_code,
                product         = excluded.product,
                grade_type      = excluded.grade_type,
                testing_charges = excluded.testing_charges,
                validity_date   = excluded.validity_date,
                remark          = excluded.remark,
                last_checked    = excluded.last_checked,
                crawl_timestamp = excluded.crawl_timestamp
            """,
            {
                "id": lab.id,
                "lab_name": lab.lab_name,
                "osl_code": lab.osl_code,
                "is_number": lab.is_number,
                "is_doc_no": lab.is_doc_no,
                "is_part": lab.is_part,
                "is_section": lab.is_section,
                "is_year": lab.is_year,
                "product": lab.product,
                "grade_type": lab.grade_type,
                "testing_charges": lab.testing_charges,
                "validity_date": lab.validity_date,
                "remark": lab.remark,
                "state": lab.state,
                "district": lab.district,
                "source_url": lab.source_url,
                "last_checked": lab.last_checked,
                "crawl_timestamp": lab.crawl_timestamp,
            },
        )

    def upsert_labs_batch(self, labs: list[BISLab]) -> int:
        """Bulk upsert labs. Returns number of records written."""
        for lab in labs:
            self.upsert_lab(lab)
        self.conn.commit()
        logger.info("Upserted %d lab records to DB", len(labs))
        return len(labs)

    def get_labs_for_standard(self, is_doc_no: str) -> list[dict]:
        """Return all lab records matching a given IS doc number."""
        cur = self.conn.execute(
            "SELECT * FROM bis_labs WHERE is_doc_no = ? ORDER BY lab_name",
            (is_doc_no,),
        )
        return [dict(row) for row in cur]

    def count_labs(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM bis_labs")
        return cur.fetchone()[0]

    # --- crawl log -------------------------------------------------------------

    def log_crawl_run(
        self,
        source: str,
        records_added: int = 0,
        records_updated: int = 0,
        errors: int = 0,
        notes: str = "",
    ) -> None:
        """Write a crawl run summary to the log table."""
        from datetime import datetime, timezone
        self.conn.execute(
            """
            INSERT INTO crawl_log (run_at, source, records_added, records_updated, errors, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                source,
                records_added,
                records_updated,
                errors,
                notes,
            ),
        )
        self.conn.commit()

    def get_crawl_stats(self) -> dict:
        """Return summary stats from the crawl log."""
        cur = self.conn.execute(
            """
            SELECT
                COUNT(*) AS runs,
                SUM(records_added) AS total_added,
                SUM(errors) AS total_errors,
                MAX(run_at) AS last_run
            FROM crawl_log
            """
        )
        row = cur.fetchone()
        return dict(row) if row else {}
