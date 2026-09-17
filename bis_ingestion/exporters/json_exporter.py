"""
exporters/json_exporter.py — Export BIS standards data to JSON / JSONL formats.

JSON export: single file containing a list of all records.
JSONL export: one JSON object per line — preferred for large datasets and
              for streaming into RAG pipelines / vector stores.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Iterator

from bis_ingestion.config import EXPORT_JSON_PATH, EXPORT_JSONL_PATH
from bis_ingestion.schemas import BISStandard

logger = logging.getLogger(__name__)


def _std_to_dict(std: BISStandard) -> dict:
    """Convert BISStandard to a JSON-serialisable dict (full fidelity)."""
    return std.model_dump()


def export_standards_to_json(
    standards: Iterable[BISStandard],
    output_path: Path = EXPORT_JSON_PATH,
    indent: int = 2,
) -> Path:
    """
    Export standards to a single JSON file.

    Args:
        standards: Iterable of BISStandard records
        output_path: Destination file path
        indent: JSON indentation (None for compact)

    Returns:
        Path to written file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records = [_std_to_dict(s) for s in standards]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=indent)
    logger.info("Exported %d standards to JSON: %s", len(records), output_path)
    return output_path


def export_standards_to_jsonl(
    standards: Iterable[BISStandard],
    output_path: Path = EXPORT_JSONL_PATH,
) -> Path:
    """
    Export standards to JSONL format (one record per line).
    Preferred for large datasets and streaming RAG pipelines.

    Args:
        standards: Iterable of BISStandard records
        output_path: Destination .jsonl file path

    Returns:
        Path to written file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for std in standards:
            f.write(json.dumps(_std_to_dict(std), ensure_ascii=False))
            f.write("\n")
            count += 1
    logger.info("Exported %d standards to JSONL: %s", count, output_path)
    return output_path


def export_db_rows_to_jsonl(
    rows: Iterable[dict],
    output_path: Path = EXPORT_JSONL_PATH,
) -> Path:
    """
    Export raw SQLite rows to JSONL.
    Deserialises JSON blob fields (amendments, labs, related_standards)
    back to native Python types.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for row in rows:
            # Expand JSON blob columns
            for field in ("amendments", "labs", "related_standards", "amendment_urls"):
                raw = row.get(field)
                if isinstance(raw, str):
                    try:
                        row[field] = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        row[field] = []
            # Convert has_mandatory_certification int back to bool/None
            cert = row.get("has_mandatory_certification")
            if cert == 1:
                row["has_mandatory_certification"] = True
            elif cert == 0:
                row["has_mandatory_certification"] = False

            f.write(json.dumps(row, ensure_ascii=False, default=str))
            f.write("\n")
            count += 1
    logger.info("Exported %d DB rows to JSONL: %s", count, output_path)
    return output_path


def iter_jsonl(path: Path) -> Iterator[dict]:
    """
    Lazily iterate over a JSONL file, yielding one dict per line.
    Useful for downstream RAG chunking without loading everything into memory.
    """
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)
