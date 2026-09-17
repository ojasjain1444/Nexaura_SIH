"""
download_and_index_free_pdfs.py — Robust downloader and full-text indexer for free public Indian Standards PDFs.

Downloads legal public deposit PDFs of Indian Standards incorporated into law,
extracts clauses & text page-by-page, and loads them into MongoDB 'nexaura' database.
"""

from __future__ import annotations

import logging
import ssl
import sys
import time
import urllib.request
from pathlib import Path

import fitz  # PyMuPDF

from bis_ingestion.config import DATA_DIR, MONGO_DB_NAME, MONGO_URI, RAG_CHUNK_OVERLAP, RAG_CHUNK_SIZE
from bis_ingestion.rag.chunker import _split_text
from bis_ingestion.schemas import RAGChunk
from bis_ingestion.storage.mongo_db import BISMongoDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("pdf_indexer")

PDF_DIR = DATA_DIR / "pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)

FREE_STANDARDS = [
    {
        "standard_number": "IS 1786:2008",
        "title": "High Strength Deformed Steel Bars and Wires for Concrete Reinforcement",
        "url": "https://archive.org/download/gov.in.is.1786.2008/is.1786.2008.pdf",
        "filename": "IS_1786_2008.pdf",
    },
    {
        "standard_number": "IS 10500:2012",
        "title": "Drinking Water - Specification (Second Revision)",
        "url": "https://archive.org/download/gov.in.is.10500.2012/is.10500.2012.pdf",
        "filename": "IS_10500_2012.pdf",
    },
    {
        "standard_number": "IS 456:2000",
        "title": "Plain and Reinforced Concrete - Code of Practice (Fourth Revision)",
        "url": "https://archive.org/download/gov.in.is.456.2000/is.456.2000.pdf",
        "filename": "IS_456_2000.pdf",
    },
    {
        "standard_number": "IS 2062:2011",
        "title": "Hot Rolled Medium and High Tensile Structural Steel",
        "url": "https://archive.org/download/gov.in.is.2062.2011/is.2062.2011.pdf",
        "filename": "IS_2062_2011.pdf",
    },
    {
        "standard_number": "IS 13920:1993",
        "title": "Ductile Detailing of Reinforced Concrete Structures Subjected to Seismic Forces",
        "url": "https://archive.org/download/gov.in.is.13920.1993/is.13920.1993.pdf",
        "filename": "IS_13920_1993.pdf",
    },
]


def download_pdf_stream(url: str, dest_path: Path, max_retries: int = 2) -> bool:
    """Download a PDF using chunked stream writing with custom SSL context."""
    if dest_path.exists() and dest_path.stat().st_size > 50000:
        logger.info("PDF already downloaded and valid: %s (%d KB)", dest_path.name, dest_path.stat().st_size // 1024)
        return True

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
    }

    for attempt in range(1, max_retries + 1):
        logger.info("Downloading %s (Attempt %d/%d)...", dest_path.name, attempt, max_retries)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=45) as resp:
                total_bytes = 0
                temp_file = dest_path.with_suffix(".tmp")
                with open(temp_file, "wb") as f:
                    while True:
                        chunk = resp.read(64 * 1024)  # 64 KB chunks
                        if not chunk:
                            break
                        f.write(chunk)
                        total_bytes += len(chunk)

                if total_bytes > 50000:
                    if temp_file.exists():
                        temp_file.replace(dest_path)
                    logger.info("Successfully downloaded %s (%d KB)", dest_path.name, total_bytes // 1024)
                    return True
                else:
                    logger.warning("Downloaded file too small (%d bytes), retrying...", total_bytes)
        except Exception as e:
            logger.warning("Download error on attempt %d for %s: %s", attempt, dest_path.name, e)
            time.sleep(2)

    return False


def extract_and_index_pdf(pdf_path: Path, standard_number: str, title: str) -> list[RAGChunk]:
    """Parse PDF page-by-page using PyMuPDF and generate RAG chunks."""
    chunks: list[RAGChunk] = []
    try:
        doc = fitz.open(str(pdf_path))
        logger.info("Parsing PDF %s (%d pages)...", pdf_path.name, len(doc))

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            raw_text = page.get_text("text").strip()
            if not raw_text or len(raw_text) < 40:
                continue

            page_num = page_idx + 1
            # Split long page text into overlapping windows
            splits = _split_text(raw_text, chunk_size=RAG_CHUNK_SIZE, overlap=RAG_CHUNK_OVERLAP)
            for split_idx, split_text in enumerate(splits):
                chunk_id = f"{standard_number.replace(':', '_').replace(' ', '_')}_P{page_num}_{split_idx}"
                formatted_text = f"[{standard_number} - Page {page_num}]\n{split_text}"
                approx_tokens = int(len(formatted_text.split()) / 0.75)
                chunks.append(
                    RAGChunk(
                        chunk_id=chunk_id,
                        standard_number=standard_number,
                        text=formatted_text,
                        token_count=approx_tokens,
                        source_url=f"local://pdfs/{pdf_path.name}#page={page_num}",
                        section=f"Page {page_num}",
                        keywords=[standard_number, "PDF_FullText"],
                    )
                )
        doc.close()
    except Exception as e:
        logger.error("Error parsing %s: %s", pdf_path.name, e)

    return chunks


def run_pipeline():
    logger.info("=" * 60)
    logger.info("STARTING FREE PUBLIC BIS PDF DOWNLOAD & INDEXING")
    logger.info("Folder: %s", PDF_DIR)
    logger.info("=" * 60)

    downloaded_count = 0
    new_chunks_count = 0

    with BISMongoDatabase(uri=MONGO_URI, db_name=MONGO_DB_NAME) as mongo:
        for item in FREE_STANDARDS:
            std_num = item["standard_number"]
            title = item["title"]
            pdf_path = PDF_DIR / item["filename"]

            # Download
            ok = download_pdf_stream(item["url"], pdf_path)
            if not ok or not pdf_path.exists():
                logger.warning("Skipping indexing for %s (download did not succeed)", std_num)
                continue

            downloaded_count += 1

            # Extract & Index
            chunks = extract_and_index_pdf(pdf_path, std_num, title)
            if chunks:
                mongo.upsert_rag_chunks_batch(chunks)
                new_chunks_count += len(chunks)
                logger.info("Indexed %d chunks into MongoDB for %s", len(chunks), std_num)

            # Update standard document in MongoDB
            mongo.standards_col.update_one(
                {"standard_number": {"$regex": f"^{std_num.split(':')[0]}", "$options": "i"}},
                {
                    "$set": {
                        "has_pdf": True,
                        "pdf_filename": item["filename"],
                        "pdf_path": str(pdf_path),
                        "pdf_pages_indexed": len(chunks),
                    }
                },
            )

        stats = mongo.get_stats()
        logger.info("=" * 60)
        logger.info("FREE PDF INDEXING COMPLETED!")
        logger.info("  - Downloaded PDFs     : %d files", downloaded_count)
        logger.info("  - Full-Text Chunks    : %d new chunks added", new_chunks_count)
        logger.info("  - Total RAG Chunks DB : %d", stats["rag_chunks_count"])
        logger.info("=" * 60)


if __name__ == "__main__":
    run_pipeline()
