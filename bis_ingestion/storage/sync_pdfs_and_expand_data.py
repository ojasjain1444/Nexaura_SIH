"""
sync_pdfs_and_expand_data.py — Store PDFs directly in MongoDB (GridFS & documents collection)
and expand the database with new industrial sectors (Solar, EV, Batteries, Helmets, Medical, Food).

Tasks:
  1. Upload all downloaded PDFs into MongoDB GridFS (`fs.files`, `fs.chunks`) + `documents` collection.
  2. Download additional free public domain standards (IS 800 Steel Code, IS 1893 Earthquake, IS 383 Aggregates).
  3. Ingest official BIS standards for key modern industries:
     - Solar & Clean Energy (PV modules, inverters)
     - Electric Vehicles & Batteries (Lithium-ion, cell safety)
     - Consumer Safety (Helmets, LED lighting, Toys, Gas cylinders)
     - Healthcare & Food (Medical devices, Milk, Drinking water, Honey)
  4. Ingest associated accredited testing laboratories.
  5. Generate semantic RAG chunks for all new standards and update MongoDB live.
"""

from __future__ import annotations

import logging
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import fitz  # PyMuPDF
import gridfs
import httpx
import pymongo

from bis_ingestion.clients.bis_standards import search_standards_api
from bis_ingestion.config import DATA_DIR, MONGO_DB_NAME, MONGO_URI, RAG_CHUNK_OVERLAP, RAG_CHUNK_SIZE
from bis_ingestion.rag.chunker import _split_text, chunk_standard
from bis_ingestion.schemas import BISLab, BISStandard, RAGChunk
from bis_ingestion.storage.mongo_db import BISMongoDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("expand_mongo")

PDF_DIR = DATA_DIR / "pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)

# Additional free public domain standards
MORE_FREE_STANDARDS = [
    {
        "standard_number": "IS 800:2007",
        "title": "General Construction in Steel - Code of Practice (Third Revision)",
        "url": "https://archive.org/download/gov.in.is.800.2007/is.800.2007.pdf",
        "filename": "IS_800_2007.pdf",
    },
    {
        "standard_number": "IS 1893:2002",
        "title": "Criteria for Earthquake Resistant Design of Structures - General Provisions",
        "url": "https://archive.org/download/gov.in.is.1893.1.2002/is.1893.1.2002.pdf",
        "filename": "IS_1893_2002.pdf",
    },
    {
        "standard_number": "IS 383:2016",
        "title": "Coarse and Fine Aggregate for Concrete - Specification (Third Revision)",
        "url": "https://archive.org/download/gov.in.is.383.1970/is.383.1970.pdf",
        "filename": "IS_383_1970.pdf",
    },
]

# New high-impact industry sectors to expand
NEW_CATEGORIES = [
    "solar", "battery", "lithium", "electric vehicle", "helmet",
    "led", "medical", "mask", "honey", "dairy", "toy",
    "gas cylinder", "transformer", "fire extinguisher", "timber",
    "glass", "fertilizer", "packaging",
]


def download_pdf_stream(url: str, dest_path: Path) -> bool:
    """Download PDF stream using chunked writing."""
    if dest_path.exists() and dest_path.stat().st_size > 50000:
        return True

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            temp_file = dest_path.with_suffix(".tmp")
            total_bytes = 0
            with open(temp_file, "wb") as f:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    total_bytes += len(chunk)
            if total_bytes > 50000:
                temp_file.replace(dest_path)
                logger.info("Saved %s (%d KB)", dest_path.name, total_bytes // 1024)
                return True
    except Exception as e:
        logger.warning("Download error for %s: %s", dest_path.name, e)
    return False


def store_pdfs_in_mongodb(mongo: BISMongoDatabase) -> int:
    """Upload all downloaded PDFs into MongoDB GridFS and 'documents' collection."""
    fs = gridfs.GridFS(mongo.db)
    docs_col = mongo.db["documents"]
    docs_col.create_index([("standard_number", pymongo.ASCENDING)], unique=True)
    docs_col.create_index([("filename", pymongo.ASCENDING)])

    stored_count = 0
    pdf_files = list(PDF_DIR.glob("*.pdf"))
    logger.info("Found %d PDF files in %s to store in MongoDB.", len(pdf_files), PDF_DIR)

    for pdf_path in pdf_files:
        filename = pdf_path.name
        # Clean standard number from filename (e.g. IS_456_2000.pdf -> IS 456:2000)
        base = pdf_path.stem
        parts = base.split("_")
        if len(parts) >= 3:
            std_num = f"{parts[0]} {parts[1]}:{parts[2]}"
        else:
            std_num = base.replace("_", " ")

        # Check page count with PyMuPDF
        try:
            doc = fitz.open(str(pdf_path))
            page_count = len(doc)
            doc.close()
        except Exception:
            page_count = 0

        file_bytes = pdf_path.read_bytes()
        size_bytes = len(file_bytes)

        # Remove existing GridFS file if updating
        existing = fs.find_one({"filename": filename})
        if existing:
            fs.delete(existing._id)

        # Put in GridFS
        grid_id = fs.put(
            file_bytes,
            filename=filename,
            contentType="application/pdf",
            standard_number=std_num,
            upload_date=datetime.now(timezone.utc),
        )

        # Upsert in documents metadata collection
        doc_record = {
            "standard_number": std_num,
            "filename": filename,
            "gridfs_id": str(grid_id),
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "page_count": page_count,
            "mime_type": "application/pdf",
            "stored_in_mongo": True,
            "local_path": str(pdf_path),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }

        docs_col.update_one(
            {"standard_number": std_num},
            {"$set": doc_record},
            upsert=True,
        )

        # Also update standards collection
        mongo.standards_col.update_one(
            {"standard_number": {"$regex": f"^{std_num.split(':')[0]}", "$options": "i"}},
            {
                "$set": {
                    "has_pdf": True,
                    "pdf_in_mongo": True,
                    "gridfs_id": str(grid_id),
                    "pdf_size_mb": round(size_bytes / (1024 * 1024), 2),
                    "page_count": page_count,
                }
            },
        )

        stored_count += 1
        logger.info("Stored in MongoDB: %s (%d KB, %d pages)", filename, size_bytes // 1024, page_count)

    return stored_count


def expand_new_industries(mongo: BISMongoDatabase, max_per_category: int = 35) -> int:
    """Fetch new sector standards from official BIS API and upsert into MongoDB."""
    seen = {doc["standard_number"] for doc in mongo.standards_col.find({}, {"standard_number": 1})}
    new_standards: list[BISStandard] = []
    new_chunks: list[RAGChunk] = []

    logger.info("Expanding database with %d new industrial sectors...", len(NEW_CATEGORIES))

    for cat in NEW_CATEGORIES:
        logger.info("Searching category: '%s'...", cat)
        items = search_standards_api(cat)
        logger.info("  Found %d standards for '%s'", len(items), cat)

        for item in items[:max_per_category]:
            std_num = (item.get("standardNumber") or "").strip().upper()
            if not std_num or std_num in seen:
                continue

            seen.add(std_num)
            withdraw_status = item.get("withdrawStatus")
            status = "WITHDRAWN" if withdraw_status == 1 else "IN FORCE"
            pub = item.get("publishedOn")
            edition_year = pub[:4] if pub and len(pub) >= 4 else None

            std = BISStandard(
                standard_number=std_num,
                title=item.get("standardName") or "",
                edition_year=edition_year,
                status=status,
                scope=f"Indian Standard specification for {item.get('standardName', '')}. Valid upto: {item.get('validUpto', 'N/A')}",
                technical_committee=str(item.get("committeeId") or ""),
                department=str(item.get("departmentId") or ""),
                source_url=f"https://standards.bis.gov.in/website/know-your-standards?standardNumber={std_num.replace(' ', '')}",
                source_system="OFFICIAL_BIS_PORTAL",
            )
            new_standards.append(std)
            new_chunks.extend(chunk_standard(std))

        time.sleep(0.8)

    if new_standards:
        mongo.upsert_standards_batch(new_standards)
        mongo.upsert_rag_chunks_batch(new_chunks)
        logger.info("Upserted %d new standards and %d new RAG chunks to MongoDB.", len(new_standards), len(new_chunks))

    return len(new_standards)


def main():
    logger.info("=" * 60)
    logger.info("EXPANDING MONGODB: STORING PDFS + INGESTING NEW SECTORS")
    logger.info("Database: %s (%s)", MONGO_DB_NAME, MONGO_URI)
    logger.info("=" * 60)

    with BISMongoDatabase(uri=MONGO_URI, db_name=MONGO_DB_NAME) as mongo:
        # 1. Download any more free standards
        for item in MORE_FREE_STANDARDS:
            dest = PDF_DIR / item["filename"]
            download_pdf_stream(item["url"], dest)

        # 2. Store all PDFs in MongoDB GridFS and documents collection
        stored_pdf_count = store_pdfs_in_mongodb(mongo)

        # 3. Expand with new modern sectors (Solar, EV, Batteries, Helmets, Healthcare)
        added_standards = expand_new_industries(mongo, max_per_category=35)

        # 4. Final summary
        stats = mongo.get_stats()
        doc_count = mongo.db["documents"].count_documents({})
        grid_files_count = mongo.db["fs.files"].count_documents({})

        logger.info("=" * 60)
        logger.info("MONGODB UPGRADE & EXPANSION COMPLETE!")
        logger.info("  - Total Standards in MongoDB : %d", stats["standards_count"])
        logger.info("  - Total Labs in MongoDB      : %d", stats["labs_count"])
        logger.info("  - Total RAG Chunks in MongoDB: %d", stats["rag_chunks_count"])
        logger.info("  - PDF Documents in MongoDB   : %d (in 'documents' collection)", doc_count)
        logger.info("  - Binary Files in GridFS     : %d (in 'fs.files' collection)", grid_files_count)
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
