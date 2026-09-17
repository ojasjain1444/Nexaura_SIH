"""
bis_ingestion — BIS Standards data ingestion pipeline for Nexaura (SIH 2026).

Package entry points:
    bis_ingestion.pipeline   — Orchestration / main run loop
    bis_ingestion.clients    — Source-specific scrapers (standards portal, LIMS)
    bis_ingestion.storage    — SQLite persistence layer
    bis_ingestion.parsers    — HTML / text parsing helpers
    bis_ingestion.exporters  — CSV / JSON / JSONL export
    bis_ingestion.rag        — RAG chunker & formatter
"""

__version__ = "0.1.0"
__author__ = "Nexaura Team — SIH 2026"
