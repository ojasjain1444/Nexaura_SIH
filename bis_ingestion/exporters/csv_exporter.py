"""
exporters/csv_exporter.py — Export BIS standards data to CSV format.

Writes a flat CSV file from the SQLite database or from an in-memory list.
All JSON blob fields (amendments, labs, related_standards) are expanded
into human-readable text columns.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Iterable

from bis_ingestion.config import EXPORT_CSV_PATH
from bis_ingestion.schemas import BISStandard

logger = logging.getLogger(__name__)

# Column order for the output CSV
_FIELDNAMES = [
    "standard_number",
    "doc_no",
    "part",
    "section",
    "edition_year",
    "title",
    "status",
    "scope",
    "ics_code",
    "technical_committee",
    "department",
    "product_category",
    "certification_scheme",
    "has_mandatory_certification",
    "publication_date",
    "reaffirmation_date",
    "withdrawal_date",
    "amendments_count",
    "amendments_summary",
    "supersedes",
    "superseded_by",
    "related_standards",
    "labs_count",
    "source_url",
    "document_url",
    "source_system",
    "last_checked",
    "crawl_timestamp",
]


def _flatten_standard(std: BISStandard) -> dict:
    """Convert a BISStandard model to a flat dict suitable for CSV."""
    amendments = std.amendments or []
    amd_summary = "; ".join(
        f"AMD {a.get('number', '?')} ({a.get('year', '?')})"
        for a in amendments
    )
    return {
        "standard_number": std.standard_number,
        "doc_no": std.doc_no or "",
        "part": std.part or "",
        "section": std.section or "",
        "edition_year": std.edition_year or "",
        "title": std.title or "",
        "status": std.status or "",
        "scope": (std.scope or "")[:500],  # truncate for CSV readability
        "ics_code": std.ics_code or "",
        "technical_committee": std.technical_committee or "",
        "department": std.department or "",
        "product_category": std.product_category or "",
        "certification_scheme": std.certification_scheme or "",
        "has_mandatory_certification": (
            "Yes" if std.has_mandatory_certification is True
            else "No" if std.has_mandatory_certification is False
            else ""
        ),
        "publication_date": std.publication_date or "",
        "reaffirmation_date": std.reaffirmation_date or "",
        "withdrawal_date": std.withdrawal_date or "",
        "amendments_count": str(len(amendments)),
        "amendments_summary": amd_summary,
        "supersedes": std.supersedes or "",
        "superseded_by": std.superseded_by or "",
        "related_standards": "; ".join(std.related_standards),
        "labs_count": str(len(std.labs)),
        "source_url": std.source_url,
        "document_url": std.document_url or "",
        "source_system": std.source_system,
        "last_checked": std.last_checked,
        "crawl_timestamp": std.crawl_timestamp,
    }


def _flatten_db_row(row: dict) -> dict:
    """Flatten a raw SQLite row dict (JSON strings for lists)."""
    amendments = json.loads(row.get("amendments") or "[]")
    related = json.loads(row.get("related_standards") or "[]")
    labs = json.loads(row.get("labs") or "[]")
    amd_summary = "; ".join(
        f"AMD {a.get('number', '?')} ({a.get('year', '?')})"
        for a in amendments
    )
    cert = row.get("has_mandatory_certification")
    return {
        "standard_number": row.get("standard_number", ""),
        "doc_no": row.get("doc_no") or "",
        "part": row.get("part") or "",
        "section": row.get("section") or "",
        "edition_year": row.get("edition_year") or "",
        "title": row.get("title") or "",
        "status": row.get("status") or "",
        "scope": (row.get("scope") or "")[:500],
        "ics_code": row.get("ics_code") or "",
        "technical_committee": row.get("technical_committee") or "",
        "department": row.get("department") or "",
        "product_category": row.get("product_category") or "",
        "certification_scheme": row.get("certification_scheme") or "",
        "has_mandatory_certification": (
            "Yes" if cert == 1 else "No" if cert == 0 else ""
        ),
        "publication_date": row.get("publication_date") or "",
        "reaffirmation_date": row.get("reaffirmation_date") or "",
        "withdrawal_date": row.get("withdrawal_date") or "",
        "amendments_count": str(len(amendments)),
        "amendments_summary": amd_summary,
        "supersedes": row.get("supersedes") or "",
        "superseded_by": row.get("superseded_by") or "",
        "related_standards": "; ".join(related),
        "labs_count": str(len(labs)),
        "source_url": row.get("source_url", ""),
        "document_url": row.get("document_url") or "",
        "source_system": row.get("source_system", ""),
        "last_checked": row.get("last_checked", ""),
        "crawl_timestamp": row.get("crawl_timestamp", ""),
    }


def export_standards_to_csv(
    standards: Iterable[BISStandard],
    output_path: Path = EXPORT_CSV_PATH,
) -> Path:
    """
    Export a list of BISStandard records to a CSV file.

    Args:
        standards: Iterable of BISStandard objects
        output_path: Destination CSV file path

    Returns:
        Path to the written file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for std in standards:
            writer.writerow(_flatten_standard(std))
            count += 1
    logger.info("Exported %d standards to CSV: %s", count, output_path)
    return output_path


def export_db_rows_to_csv(
    rows: Iterable[dict],
    output_path: Path = EXPORT_CSV_PATH,
) -> Path:
    """
    Export raw SQLite rows (dicts) to a CSV file.
    Use this when pulling directly from the database iterator.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(_flatten_db_row(row))
            count += 1
    logger.info("Exported %d DB rows to CSV: %s", count, output_path)
    return output_path
