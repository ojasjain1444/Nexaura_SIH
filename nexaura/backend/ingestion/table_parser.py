"""
table_parser.py — Phase 4: Structured Table Extraction

Project: Nexaura (SIH 2026 — SIH26107)

Extracts every table from Gemini extraction output as a structured
TableRecord. Tables are NEVER flattened to plain text only.

Stores both:
    1. Structured form: columns, rows, units, footnotes
    2. Searchable text representation (for BM25 + embedding)

BIS standards contain critical numeric tables (chemical composition,
mechanical properties, dimensional tolerances, etc.) that must be
preserved exactly.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Data Model
# =============================================================================

@dataclass
class TableRecord:
    """
    A single structured table extracted from a BIS standard.

    Two representations are stored:
    - Structured: columns, rows (for precise data retrieval)
    - search_text: flattened text (for BM25 and embedding)
    """

    table_id: str                    # Unique ID: pdf_name + "_T" + sequence
    source_table_ref: str            # Original table reference, e.g. "Table 4"
    clause: Optional[str]            # Clause this table belongs to
    page: int                        # Page number

    # Structured form
    caption: Optional[str]
    columns: list[str]               # Column headers
    rows: list[list[Any]]            # Table data rows
    units: list[str]                 # Units referenced in the table
    footnotes: list[str]             # Table footnotes

    # Searchable text
    search_text: str = ""            # Generated flat text representation

    # Provenance
    source_pdf: str = ""
    standard_number: str = ""
    needs_review: bool = False


# =============================================================================
# Table Parser
# =============================================================================

class TableParser:
    """
    Extracts and structures tables from Gemini extraction output.

    Design principles:
    - Never flatten numeric/technical tables to plain text only
    - Always store both structured and text representations
    - Preserve units exactly
    - Link every table to its parent clause
    - Generate meaningful table IDs for traceability
    """

    def parse(
        self,
        gemini_data: dict[str, Any],
        pdf_name: str,
        standard_number: str = "unknown",
    ) -> list[TableRecord]:
        """
        Extract all tables from Gemini extraction output.

        Args:
            gemini_data: Parsed JSON dict from GeminiOCR
            pdf_name: Source PDF filename
            standard_number: Standard number for ID generation

        Returns:
            List of TableRecord objects
        """
        raw_tables = gemini_data.get("tables", [])
        records: list[TableRecord] = []
        sequence = 1

        for raw in raw_tables:
            record = self._parse_single_table(
                raw, pdf_name, standard_number, sequence
            )
            if record:
                records.append(record)
                sequence += 1

        logger.info(
            "Table extraction: %s → %d tables", pdf_name, len(records)
        )
        return records

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _parse_single_table(
        self,
        raw: dict[str, Any],
        pdf_name: str,
        standard_number: str,
        sequence: int,
    ) -> Optional[TableRecord]:
        """Parse a single raw table dict into a TableRecord."""
        # Extract fields
        raw_table_id = raw.get("table_id", f"Table {sequence}")
        clause       = raw.get("clause")
        page         = raw.get("page", 0)
        caption      = raw.get("caption") or raw.get("title")
        columns      = raw.get("columns", [])
        rows         = raw.get("rows", [])
        units        = raw.get("units", [])
        footnotes    = raw.get("footnotes", [])

        # Normalize column headers
        columns = [str(c).strip() for c in columns if c is not None]

        # Normalize rows
        normalized_rows: list[list[Any]] = []
        for row in rows:
            if isinstance(row, list):
                normalized_rows.append([
                    self._normalize_cell(cell) for cell in row
                ])
            elif isinstance(row, dict):
                # Handle rows stored as dicts
                normalized_rows.append(list(row.values()))
            else:
                normalized_rows.append([str(row)])

        # Skip empty tables
        if not columns and not normalized_rows:
            logger.debug("Skipping empty table: %s", raw_table_id)
            return None

        # Generate stable table ID
        std_clean = re.sub(r"[^A-Za-z0-9]", "_", standard_number)
        table_id = f"{std_clean}_T{sequence:03d}"

        # Generate searchable text
        search_text = self._generate_search_text(
            caption=caption,
            columns=columns,
            rows=normalized_rows,
            units=units,
            footnotes=footnotes,
            clause=clause,
        )

        needs_review = (
            not columns and len(normalized_rows) > 0
        ) or (
            len(normalized_rows) == 0 and len(columns) == 0
        )

        return TableRecord(
            table_id=table_id,
            source_table_ref=raw_table_id,
            clause=clause,
            page=page,
            caption=caption,
            columns=columns,
            rows=normalized_rows,
            units=units,
            footnotes=footnotes,
            search_text=search_text,
            source_pdf=pdf_name,
            standard_number=standard_number,
            needs_review=needs_review,
        )

    def _normalize_cell(self, cell: Any) -> Any:
        """Normalize a table cell value."""
        if cell is None:
            return ""
        if isinstance(cell, (int, float)):
            return cell
        return str(cell).strip()

    def _generate_search_text(
        self,
        caption: Optional[str],
        columns: list[str],
        rows: list[list[Any]],
        units: list[str],
        footnotes: list[str],
        clause: Optional[str],
    ) -> str:
        """
        Generate a rich searchable text representation of the table.

        This is used for BM25 indexing and embedding.
        The structured data (columns/rows) is stored separately.

        Example output:
            "Table: Zinc Coating Requirements. Columns: Grade, Thickness, Minimum Mass.
             Row: A | 2.0 mm | 80 g/m2. Row: B | 3.0 mm | 140 g/m2. Units: mm g/m2."
        """
        parts: list[str] = []

        if caption:
            parts.append(f"Table: {caption}.")

        if clause:
            parts.append(f"Clause: {clause}.")

        if columns:
            parts.append(f"Columns: {', '.join(columns)}.")

        # Add rows
        for row in rows[:20]:  # Limit to first 20 rows for search text
            row_str = " | ".join(str(cell) for cell in row if cell != "")
            if row_str:
                parts.append(f"Row: {row_str}.")

        if units:
            parts.append(f"Units: {', '.join(units)}.")

        if footnotes:
            parts.append(f"Notes: {' '.join(footnotes)}.")

        return " ".join(parts)
