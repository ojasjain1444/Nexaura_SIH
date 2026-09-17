"""
ingest_api.py — FastAPI REST API for Nexaura Ingestion Monitoring and Search

Project: Nexaura (SIH 2026 — SIH26107)

Endpoints:
    GET  /health              — Service health check
    POST /ingest/start        — Start ingestion job (async background task)
    GET  /ingest/status/{job_id} — Poll job progress
    GET  /ingest/report       — Get latest processing report
    GET  /search              — Query the knowledge base (BM25-based)
    GET  /pdf/analyse         — Analyse a PDF without processing
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from nexaura.backend.api.chatbot_api import router as chatbot_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Nexaura BIS Ingestion API",
    description="REST API for BIS PDF Knowledge Base Builder (SIH 2026 — SIH26107)",
    version="1.0.0",
)
app.include_router(chatbot_router)

# In-memory job registry (in production, use Redis or DB)
_jobs: dict[str, dict] = {}

# Paths (loaded from environment or defaults)
OUTPUT_DIR = Path(os.environ.get("NEXAURA_OUTPUT_DIR", "nexaura/data/processed"))
DATA_DIR   = OUTPUT_DIR.parent


# =============================================================================
# Health
# =============================================================================

@app.get("/health")
async def health() -> dict:
    """Service health check."""
    return {
        "status": "ok",
        "service": "Nexaura BIS Ingestion API",
        "output_dir": str(OUTPUT_DIR),
    }


# =============================================================================
# Ingestion
# =============================================================================

@app.post("/ingest/start")
async def start_ingestion(
    background_tasks: BackgroundTasks,
    input_dir: str = Query(default="nexaura/data/raw", description="Input PDF directory"),
    pdf: Optional[str] = Query(default=None, description="Single PDF path to process"),
    workers: int = Query(default=1, ge=1, le=8),
    force: bool = Query(default=False),
    skip_ocr: bool = Query(default=False),
    skip_embeddings: bool = Query(default=False),
) -> dict:
    """
    Start an ingestion job in the background.

    Returns a job_id that can be polled at GET /ingest/status/{job_id}.
    """
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "input_dir": input_dir,
        "pdf": pdf,
        "workers": workers,
        "force": force,
        "error": None,
        "report": None,
    }

    background_tasks.add_task(
        _run_ingestion_job,
        job_id, input_dir, pdf, workers, force, skip_ocr, skip_embeddings,
    )

    return {"job_id": job_id, "status": "queued", "message": "Ingestion started"}


async def _run_ingestion_job(
    job_id: str,
    input_dir: str,
    pdf: Optional[str],
    workers: int,
    force: bool,
    skip_ocr: bool,
    skip_embeddings: bool,
) -> None:
    """Background task: run ingestion pipeline."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

    _jobs[job_id]["status"] = "running"
    try:
        from nexaura.backend.ingestion.pipeline import NexauraPipeline, PipelineConfig

        config = PipelineConfig(
            input_dir=Path(input_dir).resolve(),
            output_dir=OUTPUT_DIR,
            workers=workers,
            resume=not force,
            force=force,
            skip_ocr=skip_ocr,
            skip_embeddings=skip_embeddings,
            specific_pdf=Path(pdf).resolve() if pdf else None,
            gemini_api_key=os.environ.get("GEMINI_API_KEY"),
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
            postgres_url=os.environ.get("POSTGRES_URL"),
            qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
            bm25_index_path=DATA_DIR / "embeddings" / "bm25_index.pkl",
            knowledge_graph_path=OUTPUT_DIR / "knowledge_graph.json",
            processing_report_path=OUTPUT_DIR / "processing_report.json",
            failed_log_path=DATA_DIR / "logs" / "failed_files.jsonl",
            low_confidence_log_path=DATA_DIR / "logs" / "low_confidence.jsonl",
            cache_dir=DATA_DIR / "cache" / "gemini",
        )

        pipeline = NexauraPipeline(config)
        report = pipeline.run()

        _jobs[job_id].update({
            "status": "completed",
            "progress": 100,
            "report": report.to_dict(),
        })

    except Exception as exc:
        logger.error("Ingestion job %s failed: %s", job_id, exc, exc_info=True)
        _jobs[job_id].update({
            "status": "failed",
            "error": str(exc),
        })


@app.get("/ingest/status/{job_id}")
async def job_status(job_id: str) -> dict:
    """Poll ingestion job status."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@app.get("/ingest/report")
async def get_report() -> dict:
    """Get the latest processing report."""
    report_path = OUTPUT_DIR / "processing_report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="No processing report found. Run ingestion first.")
    with open(report_path, encoding="utf-8") as f:
        return json.load(f)


# =============================================================================
# Search
# =============================================================================

@app.get("/search")
async def search(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(default=10, ge=1, le=50),
) -> dict:
    """
    Search the BIS knowledge base using BM25.

    Args:
        q: Query string (natural language or IS number)
        top_k: Number of results to return

    Returns:
        JSON with ranked results including standard, clause, page, and score.
    """
    bm25_path = DATA_DIR / "embeddings" / "bm25_index.pkl"
    if not bm25_path.exists():
        raise HTTPException(
            status_code=404,
            detail="BM25 index not found. Run ingestion pipeline first."
        )

    try:
        from nexaura.backend.search.bm25 import BM25Index
        bm25 = BM25Index(index_path=bm25_path)
        bm25.load()
        results = bm25.search(q, top_k=top_k)

        return {
            "query": q,
            "top_k": top_k,
            "total_results": len(results),
            "results": [
                {
                    "rank":    r["rank"],
                    "score":   round(r["score"], 4),
                    **r.get("metadata", {}),
                }
                for r in results
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Search error: {exc}")


# =============================================================================
# PDF Analysis
# =============================================================================

@app.get("/pdf/analyse")
async def analyse_pdf(
    path: str = Query(..., description="Absolute path to PDF file"),
) -> dict:
    """Analyse a PDF without processing it."""
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF not found: {path}")

    try:
        from nexaura.backend.ingestion.pdf_detector import PDFDetector
        detector = PDFDetector()
        result = detector.analyse(pdf_path)
        return {
            "pdf_name":          result.pdf_name,
            "pdf_type":          result.pdf_type.value,
            "is_valid":          result.is_valid,
            "total_pages":       result.total_pages,
            "text_pages":        result.text_pages,
            "scanned_pages":     result.scanned_pages,
            "mixed_pages":       result.mixed_pages,
            "blank_pages":       result.blank_pages,
            "gemini_needed":     result.pages_requiring_gemini,
            "file_hash":         result.file_hash,
            "file_size_bytes":   result.file_size_bytes,
            "error_message":     result.error_message,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
