"""
pipeline.py — Main orchestration layer for the BIS Standards ingestion pipeline.

Project: Nexaura (SIH 2026 — Problem Statement SIH26107)

This module ties together:
  - BIS Standards Portal scraper (Playwright / HTTP)
  - BIS LIMS scraper (HTTP)
  - SQLite storage
  - CSV / JSON / JSONL exporters
  - RAG chunker

Entry points:
  run_full_pipeline()      — End-to-end: crawl → store → export → chunk
  run_lims_crawl()         — LIMS only
  run_standards_crawl()    — Standards portal only
  run_export()             — Export existing DB → CSV/JSON/JSONL
  run_rag_chunking()       — Build RAG chunks from DB

Usage (from Python):
    from bis_ingestion.pipeline import run_full_pipeline
    run_full_pipeline(test_mode=True)

Usage (CLI):
    python -m bis_ingestion
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bis_ingestion import __version__
from bis_ingestion.config import (
    EXPORT_CSV_PATH,
    EXPORT_JSON_PATH,
    EXPORT_JSONL_PATH,
    LIMS_IS_END,
    LIMS_IS_START,
    LOG_FILE,
    LOG_FORMAT,
    LOG_LEVEL,
    RAG_CHUNKS_JSONL_PATH,
    TEST_CRAWL_LIMIT,
)
from bis_ingestion.clients.bis_lims import crawl_lims_range, crawl_lims_search
from bis_ingestion.clients.http_client import BISHTTPClient
from bis_ingestion.exporters import (
    export_db_rows_to_jsonl,
    export_standards_to_csv,
    export_standards_to_json,
    export_standards_to_jsonl,
)
from bis_ingestion.rag import stream_chunks_from_standards, write_chunks_to_jsonl, chunk_standards_list
from bis_ingestion.schemas import BISStandard
from bis_ingestion.storage import BISDatabase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(level: str = LOG_LEVEL, log_file: Path = LOG_FILE) -> None:
    """Configure root logger to write to console and file."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=LOG_FORMAT,
        handlers=handlers,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Individual crawl runners
# ---------------------------------------------------------------------------

def run_lims_crawl(
    db: BISDatabase,
    is_start: int = LIMS_IS_START,
    is_end: int = LIMS_IS_END,
    limit: Optional[int] = None,
) -> int:
    """
    Crawl LIMS and write lab records to the database.

    Args:
        db: Open BISDatabase context
        is_start: First IS doc number to query
        is_end: Last IS doc number to query
        limit: Optional max records (for test crawls)

    Returns:
        Number of records written
    """
    logger.info(
        "Starting LIMS crawl: IS %d–%d (limit=%s)",
        is_start, is_end, limit or "none",
    )
    count = 0
    with BISHTTPClient(base_url="https://lims.bis.gov.in") as client:
        for lab in crawl_lims_range(client, is_start=is_start, is_end=is_end, limit=limit):
            db.upsert_lab(lab)
            count += 1
            if count % 50 == 0:
                db.conn.commit()
                logger.info("LIMS: %d lab records written so far", count)

    db.conn.commit()
    logger.info("LIMS crawl complete. Total records: %d", count)
    db.log_crawl_run(source="LIMS", records_added=count)
    return count


def run_standards_crawl(
    db: BISDatabase,
    queries: Optional[list[str]] = None,
    limit: int = TEST_CRAWL_LIMIT,
    use_playwright: bool = False,
) -> int:
    """
    Crawl the BIS Standards Portal using the official REST API and write standard records to DB.

    Args:
        db: Open BISDatabase context
        queries: Search terms to use. Defaults to broad category terms.
        limit: Max records per query (or total if single query)
        use_playwright: Deprecated; kept for backwards compatibility. Uses REST API.

    Returns:
        Number of records written
    """
    if queries is None:
        queries = [
            "IS 456", "cement", "steel", "concrete", "water", "electrical",
            "safety", "building", "chemical", "fire",
        ]

    logger.info("Starting Standards Portal crawl: %d queries, limit=%d", len(queries), limit)
    from bis_ingestion.clients.bis_standards import crawl_standards_api

    records = crawl_standards_api(queries=queries, limit=limit)
    count = db.upsert_standards_batch(records)
    logger.info("Standards Portal crawl complete. Wrote %d records.", count)
    db.log_crawl_run(source="BIS_STANDARDS_PORTAL", records_added=count)
    return count


# ---------------------------------------------------------------------------
# Export runner
# ---------------------------------------------------------------------------

def run_export(
    db: BISDatabase,
    csv_path: Path = EXPORT_CSV_PATH,
    json_path: Path = EXPORT_JSON_PATH,
    jsonl_path: Path = EXPORT_JSONL_PATH,
) -> dict[str, Path]:
    """
    Export all standards from the database to CSV, JSON, and JSONL.

    Args:
        db: Open BISDatabase context
        csv_path: Destination CSV file
        json_path: Destination JSON file
        jsonl_path: Destination JSONL file

    Returns:
        Dict of format → path for all written files
    """
    logger.info("Starting export run")
    rows = list(db.iter_all_standards())
    logger.info("Exporting %d standards records", len(rows))

    # We need BISStandard objects for the model-based exporters
    # Build them from raw DB rows
    import json as _json

    def row_to_std(row: dict) -> BISStandard:
        """Reconstruct a BISStandard from a raw SQLite row dict."""
        for field in ("amendments", "labs", "related_standards", "amendment_urls"):
            raw = row.get(field)
            if isinstance(raw, str):
                try:
                    row[field] = _json.loads(raw)
                except Exception:
                    row[field] = []
        cert = row.get("has_mandatory_certification")
        if cert == 1:
            row["has_mandatory_certification"] = True
        elif cert == 0:
            row["has_mandatory_certification"] = False
        else:
            row["has_mandatory_certification"] = None
        return BISStandard(**{k: v for k, v in row.items() if k in BISStandard.model_fields})

    standards = [row_to_std(r) for r in rows]

    output_csv = export_standards_to_csv(standards, csv_path)
    output_json = export_standards_to_json(standards, json_path)
    output_jsonl = export_standards_to_jsonl(standards, jsonl_path)

    logger.info("Export complete: CSV=%s, JSON=%s, JSONL=%s", output_csv, output_json, output_jsonl)
    return {"csv": output_csv, "json": output_json, "jsonl": output_jsonl}


# ---------------------------------------------------------------------------
# RAG chunking runner
# ---------------------------------------------------------------------------

def run_rag_chunking(
    db: BISDatabase,
    output_path: Path = RAG_CHUNKS_JSONL_PATH,
) -> int:
    """
    Read all standards from the DB, chunk them, and write to JSONL.

    Args:
        db: Open BISDatabase context
        output_path: Output JSONL file for RAG chunks

    Returns:
        Total number of chunks written
    """
    import json as _json

    logger.info("Starting RAG chunking")

    def row_to_std(row: dict) -> BISStandard:
        for field in ("amendments", "labs", "related_standards", "amendment_urls"):
            raw = row.get(field)
            if isinstance(raw, str):
                try:
                    row[field] = _json.loads(raw)
                except Exception:
                    row[field] = []
        cert = row.get("has_mandatory_certification")
        row["has_mandatory_certification"] = (
            True if cert == 1 else False if cert == 0 else None
        )
        return BISStandard(**{k: v for k, v in row.items() if k in BISStandard.model_fields})

    standards = [row_to_std(r) for r in db.iter_all_standards()]
    total = stream_chunks_from_standards(standards, output_path=output_path)
    logger.info("RAG chunking complete: %d chunks → %s", total, output_path)
    return total


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_full_pipeline(
    test_mode: bool = False,
    run_lims: bool = True,
    run_standards: bool = True,
    use_playwright: bool = True,
    lims_is_start: int = LIMS_IS_START,
    lims_is_end: int = LIMS_IS_END,
    standards_queries: Optional[list[str]] = None,
) -> dict:
    """
    Execute the complete ingestion pipeline end-to-end.

    Steps:
        1. Crawl BIS Standards Portal
        2. Crawl BIS LIMS
        3. Export to CSV / JSON / JSONL
        4. Generate RAG chunks

    Args:
        test_mode: If True, limit to TEST_CRAWL_LIMIT records
        run_lims: Whether to run the LIMS crawl
        run_standards: Whether to run the Standards Portal crawl
        use_playwright: Use Playwright for JS-rendered pages
        lims_is_start: First LIMS IS number to crawl
        lims_is_end: Last LIMS IS number to crawl
        standards_queries: Custom search queries for standards portal

    Returns:
        Summary dict with record counts and output paths
    """
    setup_logging()
    logger.info(
        "=== Nexaura BIS Ingestion Pipeline v%s ===",
        __version__,
    )
    logger.info(
        "Mode: %s | LIMS: %s | Standards: %s | Playwright: %s",
        "TEST" if test_mode else "FULL",
        run_lims,
        run_standards,
        use_playwright,
    )

    limit = TEST_CRAWL_LIMIT if test_mode else None
    start_time = time.time()
    summary: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "test_mode": test_mode,
        "lims_records": 0,
        "standards_records": 0,
        "rag_chunks": 0,
        "exports": {},
        "errors": [],
    }

    with BISDatabase() as db:
        # 1. Standards Portal
        if run_standards:
            try:
                n = run_standards_crawl(
                    db,
                    queries=standards_queries,
                    limit=limit or TEST_CRAWL_LIMIT,
                    use_playwright=use_playwright,
                )
                summary["standards_records"] = n
            except Exception as e:
                logger.error("Standards crawl failed: %s", e, exc_info=True)
                summary["errors"].append(f"standards: {e}")

        # 2. LIMS
        if run_lims:
            try:
                lims_limit = limit  # None = full range
                n = run_lims_crawl(
                    db,
                    is_start=lims_is_start,
                    is_end=lims_is_end if not test_mode else min(lims_is_end, lims_is_start + 49),
                    limit=lims_limit,
                )
                summary["lims_records"] = n
            except Exception as e:
                logger.error("LIMS crawl failed: %s", e, exc_info=True)
                summary["errors"].append(f"lims: {e}")

        # 3. Export
        try:
            paths = run_export(db)
            summary["exports"] = {k: str(v) for k, v in paths.items()}
        except Exception as e:
            logger.error("Export failed: %s", e, exc_info=True)
            summary["errors"].append(f"export: {e}")

        # 4. RAG chunks
        try:
            n_chunks = run_rag_chunking(db)
            summary["rag_chunks"] = n_chunks
            summary["rag_output"] = str(RAG_CHUNKS_JSONL_PATH)
        except Exception as e:
            logger.error("RAG chunking failed: %s", e, exc_info=True)
            summary["errors"].append(f"rag: {e}")

    elapsed = time.time() - start_time
    summary["elapsed_seconds"] = round(elapsed, 2)
    summary["finished_at"] = datetime.utcnow().isoformat() + "Z"

    logger.info(
        "=== Pipeline complete in %.1fs | Standards: %d | LIMS: %d | Chunks: %d ===",
        elapsed,
        summary["standards_records"],
        summary["lims_records"],
        summary["rag_chunks"],
    )
    if summary["errors"]:
        logger.warning("Pipeline finished with errors: %s", summary["errors"])

    return summary
