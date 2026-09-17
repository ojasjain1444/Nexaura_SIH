"""
sync_bis_site_to_mongo.py — Import scraped BIS site & LIMS metadata into MongoDB 'nexaura'

Project: Nexaura (SIH 2026 — SIH26107)

Reads scraped metadata from:
    - bis_ingestion/data/bis_standards.db (SQLite)
    - bis_ingestion/data/bis_standards.json
    - bis_ingestion/data/bis_standards.csv

And populates collections in MongoDB 'nexaura':
    - bis_site_standards
    - bis_site_metadata
    - documents_inventory
"""

import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from nexaura.backend.database.mongo_manager import MongoDBManager
from nexaura.backend.acquisition import InventoryManager, AccessStatus, ProcessingStatus, DocumentType

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    data_dir = PROJECT_ROOT / "bis_ingestion" / "data"
    output_dir = PROJECT_ROOT / "nexaura" / "data" / "processed"

    mongo = MongoDBManager(db_name="nexaura")
    db = mongo.get_db()

    inventory = InventoryManager(output_dir=output_dir)

    total_records = 0

    # 1. Read SQLite bis_standards.db
    db_path = data_dir / "bis_standards.db"
    if db_path.exists():
        logger.info("Reading SQLite database: %s", db_path)
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cursor.fetchall()]
            logger.info("Found SQLite tables: %s", tables)

            for table in tables:
                cursor.execute(f"SELECT * FROM {table};")
                rows = [dict(r) for r in cursor.fetchall()]
                if rows:
                    coll = db[f"bis_site_{table}"]
                    for row in rows:
                        std_num = str(row.get("standard_number") or row.get("is_number") or row.get("id") or "unknown")
                        title = str(row.get("title") or row.get("standard_title") or row.get("name") or "Untitled Standard")
                        coll.update_one({"_id_ref": std_num}, {"$set": row}, upsert=True)

                        inventory.register_document(
                            document_id=f"BIS_SITE_{std_num}",
                            title=title,
                            standard_number=std_num,
                            doc_type=DocumentType.MAIN_STANDARD,
                            source_pdf=row.get("pdf_url") or row.get("url"),
                            access_status=AccessStatus.METADATA_ONLY if not row.get("pdf_url") else AccessStatus.DOWNLOADED,
                            processing_status=ProcessingStatus.PENDING,
                            extra_metadata=row,
                        )
                    total_records += len(rows)
                    logger.info("Imported %d rows from SQLite table '%s' into MongoDB 'nexaura.bis_site_%s'", len(rows), table, table)
            conn.close()
        except Exception as exc:
            logger.error("Failed to import SQLite data: %s", exc)

    # 2. Read JSON bis_standards.json if present
    json_path = data_dir / "bis_standards.json"
    if json_path.exists():
        logger.info("Reading JSON file: %s", json_path)
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                records = json.load(f)

            if isinstance(records, list):
                logger.info("Found %d records in bis_standards.json", len(records))
                coll = db["bis_site_standards_json"]
                for rec in records:
                    std_num = str(rec.get("standard_number") or rec.get("is_number") or rec.get("id") or "unknown")
                    title = str(rec.get("title") or rec.get("standard_title") or rec.get("name") or "Untitled Standard")
                    coll.update_one({"standard_number": std_num}, {"$set": rec}, upsert=True)

                    inventory.register_document(
                        document_id=f"BIS_JSON_{std_num}",
                        title=title,
                        standard_number=std_num,
                        doc_type=DocumentType.MAIN_STANDARD,
                        source_pdf=rec.get("pdf_url") or rec.get("url"),
                        access_status=AccessStatus.METADATA_ONLY if not rec.get("pdf_url") else AccessStatus.DOWNLOADED,
                        processing_status=ProcessingStatus.PENDING,
                        extra_metadata=rec,
                    )
                total_records += len(records)
                logger.info("Imported %d records into MongoDB 'nexaura.bis_site_standards_json'", len(records))
        except Exception as exc:
            logger.error("Failed to import JSON data: %s", exc)

    # 3. Export Inventory & Coverage to MongoDB
    reports = inventory.export_reports()
    with open(reports["documents_inventory"], "r", encoding="utf-8") as f1:
        inv_payload = json.load(f1)
    with open(reports["document_coverage_report"], "r", encoding="utf-8") as f2:
        cov_payload = json.load(f2)

    from nexaura.backend.database.mongo_repository import MongoRepository
    repo = MongoRepository(mongo)
    repo.save_inventory_and_coverage(inv_payload, cov_payload)

    print("\n" + "=" * 60)
    print("  BIS SITE DATA SYNC TO MONODB 'nexaura' COMPLETE")
    print("=" * 60)
    print(f"  Total Imported Records:  {total_records}")
    print(f"  Target Database:         nexaura")
    print(f"  Target Host:             mongodb://localhost:27017")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
