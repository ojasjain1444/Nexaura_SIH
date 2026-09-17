"""
metadata_extractor.py — Document-Level Metadata Extraction

Project: Nexaura (SIH 2026 — SIH26107)

Extracts and normalizes document-level metadata from Gemini output.

Rules:
    - Never infer unknown fields — mark as "unknown"
    - Normalize standard numbers to consistent format
    - Cross-reference with bis_ingestion SQLite if available (read-only)
    - Never convert "unknown" status to "in_force"
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# Normalize IS standard number: "IS456" → "IS 456", "is 456:2000" → "IS 456"
IS_NUMBER_RE = re.compile(
    r"(?:IS|I\.S\.)\s*(\d+(?:\s*Part\s*\d+)?(?:\s*Sec\s*\d+)?)",
    re.IGNORECASE,
)

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


@dataclass
class DocumentMetadata:
    """Document-level metadata for a BIS standard."""

    # Identity
    standard_number: str = "unknown"
    title: Optional[str] = None
    edition: Optional[str] = None
    year: Optional[int] = None
    part: Optional[str] = None
    section: Optional[str] = None
    amendment: Optional[str] = None

    # Status
    status: str = "unknown"       # Never inferred — only from source evidence
    publication_date: Optional[str] = None
    reaffirmation_date: Optional[str] = None

    # Scope and foreword
    scope: Optional[str] = None
    foreword: Optional[str] = None

    # Classification
    ics_code: Optional[str] = None
    technical_committee: Optional[str] = None

    # Relationships (evidence-based only)
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    amended_by: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)

    # Provenance
    source_pdf: str = ""
    extraction_method: str = "gemini_flash"
    needs_review: bool = False


class MetadataExtractor:
    """
    Extracts and normalizes document-level metadata from Gemini output.

    Reads the top-level fields from the Gemini extraction dict.
    Normalizes standard numbers, years, and status values.
    Never invents or infers unavailable information.
    """

    def extract(
        self,
        gemini_data: dict[str, Any],
        pdf_name: str,
    ) -> DocumentMetadata:
        """
        Extract metadata from Gemini extraction output.

        Args:
            gemini_data: Parsed JSON dict from GeminiOCR
            pdf_name: Source PDF filename (fallback for standard number)

        Returns:
            DocumentMetadata
        """
        raw_std = gemini_data.get("standard_number", "")
        standard_number = self._normalize_standard_number(raw_std)

        if not standard_number and pdf_name:
            fn_clean = pdf_name.replace("_", " ").replace("-", " ")
            m = IS_NUMBER_RE.search(fn_clean)
            if m:
                standard_number = f"IS {m.group(1).strip()}".upper()

        standard_number = standard_number or "unknown"

        raw_year = gemini_data.get("year")
        year = self._parse_year(raw_year)

        edition = gemini_data.get("edition")
        if not year and edition:
            year = self._parse_year(edition)

        references = gemini_data.get("references", [])
        if isinstance(references, list):
            references = [r for r in references if isinstance(r, str) and r.strip()]
        else:
            references = []

        meta = DocumentMetadata(
            standard_number=standard_number,
            title=gemini_data.get("title") or None,
            edition=str(edition) if edition else None,
            year=year,
            part=gemini_data.get("part") or None,
            amendment=gemini_data.get("amendment") or None,
            status="unknown",     # Never inferred from OCR
            scope=gemini_data.get("scope") or None,
            foreword=gemini_data.get("foreword") or None,
            references=references,
            source_pdf=pdf_name,
            needs_review=bool(gemini_data.get("needs_review", False)),
        )

        logger.info(
            "Metadata extracted: standard=%s title=%s year=%s",
            meta.standard_number,
            (meta.title or "")[:60],
            meta.year,
        )
        return meta

    def _normalize_standard_number(self, raw: Any) -> Optional[str]:
        """Normalize IS standard number to 'IS XXXX' format."""
        if not raw:
            return None
        raw_str = str(raw).strip()
        m = IS_NUMBER_RE.search(raw_str)
        if m:
            num = re.sub(r"\s+", " ", m.group(1).strip())
            return f"IS {num}".upper()
        # Return as-is if no IS pattern (might be a different standard type)
        cleaned = raw_str.strip()
        return cleaned if cleaned else None

    def _parse_year(self, value: Any) -> Optional[int]:
        """Extract a 4-digit year from a value."""
        if value is None:
            return None
        if isinstance(value, int) and 1900 <= value <= 2100:
            return value
        m = YEAR_RE.search(str(value))
        if m:
            return int(m.group())
        return None
