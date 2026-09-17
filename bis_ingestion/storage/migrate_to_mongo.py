"""
migrate_to_mongo.py — Seamlessly migrate existing SQLite & JSONL data to MongoDB.

Migrates:
  1. `bis_standards` from SQLite -> MongoDB collection `standards`
  2. `bis_labs` from SQLite -> MongoDB collection `labs`
  3. `rag_chunks.jsonl` -> MongoDB collection `rag_chunks`
  4. Crawl logs -> MongoDB collection `crawl_log`

Usage:
  python -m bis_ingestion.storage.migrate_to_mongo
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path

from bis_ingestion.config import (
    MONGO_DB_NAME,
    MONGO_URI,
    RAG_CHUNKS_JSONL_PATH,
    SQLITE_DB_PATH,
)
from bis_ingestion.storage.mongo_db import BISMongoDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("migrate_to_mongo")


def migrate_sqlite_standards(conn: sqlite3.Connection, mongo: BISMongoDatabase) -> int:
    """Read standards from SQLite and insert into MongoDB."""
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bis_standards")
    rows = cursor.fetchall()
    logger.info("Found %d standards in SQLite DB.", len(rows))

    standards_list = []
    for r in rows:
        d = dict(r)
        # Parse JSON string fields
        for field in ("amendments", "labs", "related_standards", "amendment_urls"):
            val = d.get(field)
            if isinstance(val, str) and val.strip():
                try:
                    d[field] = json.loads(val)
                except Exception:
                    d[field] = []
            elif val is None:
                d[field] = []

        # Convert certification integer to boolean
        cert = d.get("has_mandatory_certification")
        if cert == 1:
            d["has_mandatory_certification"] = True
        elif cert == 0:
            d["has_mandatory_certification"] = False
        else:
            d["has_mandatory_certification"] = None

        standards_list.append(d)

    n = mongo.upsert_standards_batch(standards_list)
    logger.info("Migrated %d standards to MongoDB collection 'standards'.", n)
    return n


def migrate_sqlite_labs(conn: sqlite3.Connection, mongo: BISMongoDatabase) -> int:
    """Read labs from SQLite and insert into MongoDB."""
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bis_labs")
    rows = cursor.fetchall()
    logger.info("Found %d labs in SQLite DB.", len(rows))

    labs_list = [dict(r) for r in rows]
    n = mongo.upsert_labs_batch(labs_list)
    logger.info("Migrated %d labs to MongoDB collection 'labs'.", n)
    return n


def migrate_rag_chunks(chunks_file: Path, mongo: BISMongoDatabase) -> int:
    """Read RAG chunks from JSONL and insert into MongoDB."""
    if not chunks_file.exists():
        logger.warning("RAG chunks file not found: %s", chunks_file)
        return 0

    chunks = []
    with open(chunks_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    chunks.append(json.loads(line))
                except Exception as e:
                    logger.warning("Skipping malformed chunk: %s", e)

    logger.info("Found %d RAG chunks in %s.", len(chunks), chunks_file.name)
    n = mongo.upsert_rag_chunks_batch(chunks)
    logger.info("Migrated %d RAG chunks to MongoDB collection 'rag_chunks'.", n)
    return n


def run_migration():
    logger.info("=" * 60)
    logger.info("Starting Migration to MongoDB ('%s')", MONGO_DB_NAME)
    logger.info("Target URI: %s", MONGO_URI)
    logger.info("=" * 60)

    # 1. Connect to SQLite
    if not SQLITE_DB_PATH.exists():
        logger.error("SQLite database not found at %s", SQLITE_DB_PATH)
        return 1

    conn = sqlite3.connect(str(SQLITE_DB_PATH))

    # 2. Connect to MongoDB
    with BISMongoDatabase(uri=MONGO_URI, db_name=MONGO_DB_NAME) as mongo:
        std_count = migrate_sqlite_standards(conn, mongo)
        lab_count = migrate_sqlite_labs(conn, mongo)
        chunk_count = migrate_rag_chunks(RAG_CHUNKS_JSONL_PATH, mongo)

        # Log migration run
        mongo.log_crawl_run(
            source="SQLITE_TO_MONGO_MIGRATION",
            records_added=std_count + lab_count,
            notes=f"Migrated {std_count} standards, {lab_count} labs, {chunk_count} RAG chunks",
        )

        stats = mongo.get_stats()
        logger.info("=" * 60)
        logger.info("MongoDB Migration Complete!")
        logger.info("  - Standards in Mongo: %d", stats["standards_count"])
        logger.info("  - Labs in Mongo     : %d", stats["labs_count"])
        logger.info("  - Chunks in Mongo   : %d", stats["rag_chunks_count"])
        logger.info("=" * 60)

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(run_migration())
