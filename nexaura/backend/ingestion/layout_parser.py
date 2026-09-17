"""
layout_parser.py — Phase 3a: Layout Understanding and Heading Reconstruction

Project: Nexaura (SIH 2026 — SIH26107)

Transforms raw Gemini extraction output (or PyMuPDF text blocks) into
a structured layout representation that clause_parser.py can consume.

Responsibilities:
- Identify IS standard heading patterns
- Detect section boundaries
- Reconstruct reading order
- Normalize whitespace and encoding
- Mark heading candidates for clause_parser
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# IS Standard Clause Pattern Regex
# =============================================================================

# Matches patterns like: 5   5.1   5.2.1   5.2.1.1   A-1   B.2   Annex A
CLAUSE_NUMBER_PATTERN = re.compile(
    r"^("
    r"\d+(?:\.\d+)*"           # Numeric: 5, 5.1, 5.2.1, 5.2.1.1
    r"|[A-Z]-\d+(?:\.\d+)*"   # Annex-style: A-1, B-2.1
    r"|[A-Z]\.\d+(?:\.\d+)*"  # Dot-annex: A.1, B.2.1
    r")\s+"
    r"(.+)$"
)

# Matches heading-only lines (all caps or title case, short)
HEADING_PATTERN = re.compile(
    r"^[A-Z][A-Z\s\-–—]{2,60}$"
)


# =============================================================================
# Data models
# =============================================================================

@dataclass
class LayoutBlock:
    """A single layout block in reading order."""
    block_id: int
    text: str
    page: int
    is_heading: bool = False
    is_clause_start: bool = False
    clause_number: Optional[str] = None
    heading_text: Optional[str] = None
    font_size: float = 0.0
    is_bold: bool = False


@dataclass
class LayoutResult:
    """Layout analysis result for a PDF document."""
    pdf_name: str
    blocks: list[LayoutBlock] = field(default_factory=list)
    total_pages: int = 0


# =============================================================================
# Layout Parser
# =============================================================================

class LayoutParser:
    """
    Reconstructs document layout from Gemini extraction output.

    Normalizes the raw clause list from Gemini into a clean,
    ordered sequence of layout blocks suitable for clause_parser.py.
    """

    def parse_gemini_output(
        self,
        gemini_data: dict,
        pdf_name: str,
    ) -> LayoutResult:
        """
        Parse Gemini extraction output into layout blocks.

        Args:
            gemini_data: The parsed JSON dict from GeminiOCR
            pdf_name: Source PDF name (for logging)

        Returns:
            LayoutResult with ordered layout blocks
        """
        blocks: list[LayoutBlock] = []
        block_id = 0

        # Process scope as a special block
        scope = gemini_data.get("scope")
        if scope and scope.strip():
            blocks.append(LayoutBlock(
                block_id=block_id,
                text=scope.strip(),
                page=1,
                is_heading=False,
                is_clause_start=True,
                clause_number="SCOPE",
                heading_text="SCOPE",
            ))
            block_id += 1

        # Process foreword
        foreword = gemini_data.get("foreword")
        if foreword and foreword.strip():
            blocks.append(LayoutBlock(
                block_id=block_id,
                text=foreword.strip(),
                page=1,
                is_heading=False,
                is_clause_start=True,
                clause_number="FOREWORD",
                heading_text="FOREWORD",
            ))
            block_id += 1

        # Process definitions
        for defn in gemini_data.get("definitions", []):
            term = defn.get("term", "").strip()
            definition = defn.get("definition", "").strip()
            clause = defn.get("clause", "")
            page = defn.get("page", 1)
            if term and definition:
                blocks.append(LayoutBlock(
                    block_id=block_id,
                    text=f"{term}: {definition}",
                    page=page,
                    is_clause_start=True,
                    clause_number=clause or "DEF",
                    heading_text=term,
                ))
                block_id += 1

        # Process clauses (main content)
        for clause_data in gemini_data.get("clauses", []):
            clause_text = clause_data.get("text", "").strip()
            if not clause_text:
                continue
            clause_num = str(clause_data.get("clause", "")).strip()
            heading = clause_data.get("heading", "") or ""
            page = clause_data.get("page", 1)

            # Parse clause number from text if not provided
            if not clause_num:
                match = CLAUSE_NUMBER_PATTERN.match(clause_text)
                if match:
                    clause_num = match.group(1)
                    heading = heading or match.group(2)

            is_clause = bool(clause_num and CLAUSE_NUMBER_PATTERN.match(
                f"{clause_num} {heading or 'X'}"
            ))

            blocks.append(LayoutBlock(
                block_id=block_id,
                text=clause_text,
                page=page,
                is_clause_start=is_clause,
                clause_number=clause_num,
                heading_text=heading.strip() or None,
            ))
            block_id += 1

        # Process annexures
        for annex in gemini_data.get("annexures", []):
            annex_id = annex.get("annex_id", "").strip()
            annex_title = annex.get("title", "").strip()
            annex_text = annex.get("text", "").strip()
            page = annex.get("page", 1)
            if annex_text:
                blocks.append(LayoutBlock(
                    block_id=block_id,
                    text=annex_text,
                    page=page,
                    is_clause_start=True,
                    clause_number=annex_id or "ANNEX",
                    heading_text=annex_title or annex_id,
                ))
                block_id += 1

        total_pages = max((b.page for b in blocks), default=1)

        logger.info(
            "Layout parsed: %s → %d blocks across %d pages",
            pdf_name, len(blocks), total_pages,
        )

        return LayoutResult(
            pdf_name=pdf_name,
            blocks=blocks,
            total_pages=total_pages,
        )

    def parse_text_extraction(
        self,
        text_result,  # TextExtractionResult
        pdf_name: str,
    ) -> LayoutResult:
        """
        Parse PyMuPDF text extraction output into layout blocks.
        Used for text-layer pages that don't go through Gemini.

        Args:
            text_result: TextExtractionResult from text_extractor.py
            pdf_name: Source PDF name

        Returns:
            LayoutResult with ordered layout blocks
        """
        blocks: list[LayoutBlock] = []
        block_id = 0

        for page in text_result.pages:
            for tb in page.blocks:
                text = tb.text.strip()
                if not text:
                    continue

                # Check if this is a clause start
                m = CLAUSE_NUMBER_PATTERN.match(text)
                if m:
                    clause_num = m.group(1)
                    heading = m.group(2).strip()
                    # The heading is on this line; text may continue
                    blocks.append(LayoutBlock(
                        block_id=block_id,
                        text=text,
                        page=page.page_number,
                        is_heading=tb.is_heading_candidate,
                        is_clause_start=True,
                        clause_number=clause_num,
                        heading_text=heading,
                        font_size=tb.font_size,
                        is_bold=tb.is_bold,
                    ))
                else:
                    blocks.append(LayoutBlock(
                        block_id=block_id,
                        text=text,
                        page=page.page_number,
                        is_heading=tb.is_heading_candidate,
                        font_size=tb.font_size,
                        is_bold=tb.is_bold,
                    ))
                block_id += 1

        return LayoutResult(
            pdf_name=pdf_name,
            blocks=blocks,
            total_pages=text_result.total_pages,
        )
