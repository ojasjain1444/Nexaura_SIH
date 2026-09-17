"""
jsonl_exporter.py — JSONL Output Writers

Project: Nexaura (SIH 2026 — SIH26107)

Writes all pipeline outputs to JSONL and JSON files.

Files produced:
    nexaura/data/processed/
        clauses.jsonl       — one KnowledgeUnit per line
        tables.jsonl        — one TableRecord per line
        features.jsonl      — one TechnicalParameter per line
        documents.jsonl     — one document summary per line
        metadata.json       — aggregate document metadata dict
        knowledge_graph.json — graph structure
        processing_report.json — run statistics
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Low-level JSONL writer
# =============================================================================

def append_jsonl(path: Path, records: list[dict[str, Any]]) -> int:
    """
    Append records to a JSONL file.

    Args:
        path: Output JSONL file path.
        records: List of dicts to write.

    Returns:
        Number of records written.
    """
    if not records:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(path, "a", encoding="utf-8") as f:
        for record in records:
            try:
                f.write(json.dumps(record, ensure_ascii=False, default=_json_default) + "\n")
                count += 1
            except Exception as exc:
                logger.warning("JSONL write failed for record: %s", exc)
    return count


def write_json(path: Path, data: Any) -> None:
    """Write a JSON file (overwrites)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=_json_default)


def _json_default(obj: Any) -> Any:
    """JSON serialization fallback for non-standard types."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


# =============================================================================
# Typed exporters
# =============================================================================

class NexauraExporter:
    """
    Manages all JSONL/JSON output files for a pipeline run.

    Creates files in output_dir and appends records incrementally
    so that partial runs are preserved on failure.
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.clauses_path   = self.output_dir / "clauses.jsonl"
        self.tables_path    = self.output_dir / "tables.jsonl"
        self.features_path  = self.output_dir / "features.jsonl"
        self.docs_path      = self.output_dir / "documents.jsonl"
        self.metadata_path  = self.output_dir / "metadata.json"
        self.graph_path     = self.output_dir / "knowledge_graph.json"
        self.report_path    = self.output_dir / "processing_report.json"

        self._metadata_store: dict[str, Any] = {}

    def export_knowledge_units(self, knowledge_units: list) -> int:
        """
        Export a list of KnowledgeUnit objects to clauses.jsonl.

        Args:
            knowledge_units: List of KnowledgeUnit objects.

        Returns:
            Number of records written.
        """
        records = [ku.model_dump() for ku in knowledge_units]
        written = append_jsonl(self.clauses_path, records)
        logger.debug("Exported %d clauses to %s", written, self.clauses_path)
        return written

    def export_tables(self, tables: list) -> int:
        """Export TableRecord objects to tables.jsonl."""
        records = [self._table_to_dict(t) for t in tables]
        written = append_jsonl(self.tables_path, records)
        logger.debug("Exported %d tables to %s", written, self.tables_path)
        return written

    def export_features(self, knowledge_units: list) -> int:
        """Export TechnicalParameter records to features.jsonl."""
        records = []
        for ku in knowledge_units:
            for param in ku.technical_parameters:
                record = {
                    "knowledge_unit_id": ku.id,
                    "standard_number":   ku.standard_number,
                    "clause":            ku.clause,
                    "page_start":        ku.page_start,
                    **param.model_dump(),
                }
                records.append(record)
        written = append_jsonl(self.features_path, records)
        logger.debug("Exported %d features to %s", written, self.features_path)
        return written

    def export_document_summary(
        self,
        pdf_name: str,
        metadata,
        clauses_count: int,
        tables_count: int,
        features_count: int,
        avg_confidence: float,
        pdf_type: str,
        total_pages: int,
        gemini_pages: int,
    ) -> None:
        """Export a one-line document summary to documents.jsonl."""
        record = {
            "pdf_name":        pdf_name,
            "standard_number": metadata.standard_number if metadata else "unknown",
            "title":           metadata.title if metadata else None,
            "edition":         metadata.edition if metadata else None,
            "year":            metadata.year if metadata else None,
            "part":            metadata.part if metadata else None,
            "status":          metadata.status if metadata else "unknown",
            "pdf_type":        pdf_type,
            "total_pages":     total_pages,
            "gemini_pages":    gemini_pages,
            "clauses":         clauses_count,
            "tables":          tables_count,
            "features":        features_count,
            "avg_confidence":  round(avg_confidence, 4),
            "exported_at":     datetime.now(timezone.utc).isoformat(),
        }
        append_jsonl(self.docs_path, [record])

        # Also accumulate into metadata store
        if metadata and metadata.standard_number:
            self._metadata_store[metadata.standard_number] = {
                "standard_number": metadata.standard_number,
                "title":           metadata.title,
                "edition":         metadata.edition,
                "year":            metadata.year,
                "status":          metadata.status,
                "scope":           metadata.scope,
                "source_pdf":      pdf_name,
            }

    def save_metadata_index(self) -> None:
        """Write the aggregate metadata.json index."""
        write_json(self.metadata_path, {
            "total_standards": len(self._metadata_store),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "standards": list(self._metadata_store.values()),
        })
        logger.info("Metadata index saved: %s (%d standards)", self.metadata_path, len(self._metadata_store))

    def save_processing_report(self, report_dict: dict) -> None:
        """Write the processing report JSON."""
        write_json(self.report_path, report_dict)
        logger.info("Processing report saved: %s", self.report_path)

    def save_knowledge_graph(self, graph_dict: dict) -> None:
        """Write the knowledge graph JSON."""
        write_json(self.graph_path, graph_dict)
        logger.info("Knowledge graph saved: %s", self.graph_path)

    def get_output_summary(self) -> dict:
        """Return a summary of all output files."""
        files = {
            "clauses":  self.clauses_path,
            "tables":   self.tables_path,
            "features": self.features_path,
            "documents":self.docs_path,
            "metadata": self.metadata_path,
            "graph":    self.graph_path,
            "report":   self.report_path,
        }
        return {
            name: {
                "path":   str(path),
                "exists": path.exists(),
                "size_kb": round(path.stat().st_size / 1024, 1) if path.exists() else 0,
            }
            for name, path in files.items()
        }

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _table_to_dict(self, table) -> dict:
        return {
            "table_id":         table.table_id,
            "source_table_ref": table.source_table_ref,
            "clause":           table.clause,
            "page":             table.page,
            "caption":          table.caption,
            "columns":          table.columns,
            "rows":             table.rows,
            "units":            table.units,
            "footnotes":        table.footnotes,
            "search_text":      table.search_text,
            "source_pdf":       table.source_pdf,
            "standard_number":  table.standard_number,
            "needs_review":     table.needs_review,
        }
