"""
populate_full_mongo.py — Ingest comprehensive official BIS Standards & Labs directly into MongoDB.

Fetches live official metadata across key Indian Standard categories:
  - Civil & Construction (Concrete, Cement, Steel, Bricks)
  - Water & Environment (Drinking water, Sewage, Filtration)
  - Electrical & Electronics (Transformers, Cables, Safety)
  - Fire & Safety (Fire extinguishers, PPE, Alarms)
  - Mechanical & Materials (Aluminium, Copper, Fasteners)
  - Food & Agriculture (Pesticides, Packaging, Edible oils)

Writes directly to MongoDB 'nexaura' database:
  - `standards`
  - `labs`
  - `rag_chunks`
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from bis_ingestion.clients.bis_standards import search_standards_api
from bis_ingestion.config import HEADERS, MONGO_DB_NAME, MONGO_URI, REQUEST_TIMEOUT
from bis_ingestion.rag.chunker import chunk_standard
from bis_ingestion.schemas import BISLab, BISStandard, RAGChunk
from bis_ingestion.storage.mongo_db import BISMongoDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("populate_mongo")

CATEGORIES = [
    "IS 456", "concrete", "cement", "steel", "IS 1786",
    "water", "electrical", "safety", "fire", "building",
    "brick", "plastic", "cable", "paint", "pipe",
]


def fetch_labs_for_standard_api(standard_enc_id: str, is_number: str) -> list[BISLab]:
    """Fetch testing laboratories for a standard from official BIS review service."""
    url = "https://standardsadmin.bis.gov.in/review-service/getStandardLaboratoryDetails"
    payload = {"standardId": standard_enc_id, "page": 1, "limit": 20, "searchText": ""}
    headers = {
        **HEADERS,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://standards.bis.gov.in",
        "Referer": "https://standards.bis.gov.in/",
    }

    labs: list[BISLab] = []
    try:
        with httpx.Client(verify=False, timeout=REQUEST_TIMEOUT) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json().get("data", []) or []
                for item in data:
                    lab_name = item.get("labName")
                    if not lab_name:
                        continue
                    labs.append(
                        BISLab(
                            lab_name=lab_name.strip(),
                            osl_code=str(item.get("oslCode") or ""),
                            is_number=is_number,
                            product=item.get("labCity") or item.get("labState") or "Testing Services",
                            state=item.get("labState"),
                            district=item.get("labDistrict"),
                            remark=f"{item.get('labAddress', '')} | Contact: {item.get('contactPerson', '')} ({item.get('contactNumber', '')})",
                            source_url=f"https://standards.bis.gov.in/website/know-your-standards?standardNumber={is_number}",
                        )
                    )
    except Exception as e:
        logger.warning("Could not fetch labs for %s: %s", is_number, e)

    return labs


def run_full_mongo_ingestion(max_per_category: int = 50):
    logger.info("=" * 60)
    logger.info("Starting Full Ingestion into MongoDB ('%s')", MONGO_DB_NAME)
    logger.info("Target: %s", MONGO_URI)
    logger.info("=" * 60)

    seen_standards: set[str] = set()
    total_standards: list[BISStandard] = []
    total_labs: list[BISLab] = []
    total_chunks: list[RAGChunk] = []

    with BISMongoDatabase(uri=MONGO_URI, db_name=MONGO_DB_NAME) as mongo:
        for cat in CATEGORIES:
            logger.info("Querying category: '%s'...", cat)
            items = search_standards_api(cat)
            logger.info("  Found %d standards for '%s'", len(items), cat)

            for item in items[:max_per_category]:
                std_num = (item.get("standardNumber") or "").strip().upper()
                if not std_num or std_num in seen_standards:
                    continue

                seen_standards.add(std_num)

                # Status
                withdraw_status = item.get("withdrawStatus")
                status = "WITHDRAWN" if withdraw_status == 1 else "IN FORCE"

                # Year
                pub = item.get("publishedOn")
                edition_year = pub[:4] if pub and len(pub) >= 4 else None

                std = BISStandard(
                    standard_number=std_num,
                    title=item.get("standardName") or "",
                    edition_year=edition_year,
                    status=status,
                    scope=f"Standard for {item.get('standardName', '')}. Valid upto: {item.get('validUpto', 'N/A')}",
                    technical_committee=str(item.get("committeeId") or ""),
                    department=str(item.get("departmentId") or ""),
                    source_url=f"https://standards.bis.gov.in/website/know-your-standards?standardNumber={std_num.replace(' ', '')}",
                    source_system="OFFICIAL_BIS_PORTAL",
                )
                total_standards.append(std)

                # Generate RAG chunks for this standard
                chunks = chunk_standard(std)
                total_chunks.extend(chunks)

                # Fetch labs for high-priority standards (IS 456, IS 1786, etc.)
                enc_id = item.get("standardEncId")
                if enc_id and any(k in std_num for k in ["IS 456", "IS 1786", "IS 269", "IS 12269", "IS 800", "IS 13920"]):
                    time.sleep(0.5)
                    labs = fetch_labs_for_standard_api(enc_id, std_num)
                    total_labs.extend(labs)

            # Polite delay between search requests
            time.sleep(1.0)

        # Batch upsert to MongoDB
        logger.info("Upserting %d standards to MongoDB...", len(total_standards))
        mongo.upsert_standards_batch(total_standards)

        if total_labs:
            logger.info("Upserting %d labs to MongoDB...", len(total_labs))
            mongo.upsert_labs_batch(total_labs)

        logger.info("Upserting %d RAG chunks to MongoDB...", len(total_chunks))
        mongo.upsert_rag_chunks_batch(total_chunks)

        stats = mongo.get_stats()
        logger.info("=" * 60)
        logger.info("FULL MONGO INGESTION COMPLETED SUCCESSFULLY!")
        logger.info("Total Standards in MongoDB : %d", stats["standards_count"])
        logger.info("Total Labs in MongoDB      : %d", stats["labs_count"])
        logger.info("Total RAG Chunks in MongoDB: %d", stats["rag_chunks_count"])
        logger.info("=" * 60)


if __name__ == "__main__":
    run_full_mongo_ingestion(max_per_category=40)
