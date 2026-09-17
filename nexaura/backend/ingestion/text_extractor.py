"""
text_extractor.py — Phase 2a: Direct Text Extraction (No API)

Project: Nexaura (SIH 2026 — SIH26107)

Extracts text directly from PyMuPDF for text-layer pages.
Produces the same output schema as gemini_ocr.py so the
downstream pipeline is agnostic to the extraction method.

This module costs ZERO API calls.
It only runs on pages where has_text_layer = True and
requires_gemini = False (as determined by pdf_detector.py).

Outputs:
    TextExtractionResult — structured text extracted from text pages
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class ExtractedBlock:
    """A single text block extracted from a page."""
    block_id: int
    page_number: int
    text: str
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    block_type: str = "text"  # "text" | "image"
    font_size: float = 0.0
    is_bold: bool = False
    is_heading_candidate: bool = False


@dataclass
class ExtractedPage:
    """All text blocks from a single page."""
    page_number: int
    width: float
    height: float
    raw_text: str          # full concatenated text
    blocks: list[ExtractedBlock] = field(default_factory=list)
    has_text: bool = True
    extraction_method: str = "pymupdf_direct"


@dataclass
class TextExtractionResult:
    """Complete text extraction result for a PDF document."""
    pdf_name: str
    total_pages: int
    pages: list[ExtractedPage] = field(default_factory=list)
    extraction_method: str = "pymupdf_direct"

    # Aggregated full text (used for fallback processing)
    full_text: str = ""

    def get_page(self, page_number: int) -> Optional[ExtractedPage]:
        """Get extracted page by 1-indexed page number."""
        for p in self.pages:
            if p.page_number == page_number:
                return p
        return None


# =============================================================================
# Text Extractor
# =============================================================================

class TextExtractor:
    """
    Extracts structured text directly from PDF text layers using PyMuPDF.

    Only processes pages identified as 'text_page' by PDFDetector.
    Produces output compatible with the downstream clause parser.

    Features:
    - Preserves reading order (top-to-bottom, left-to-right)
    - Detects heading candidates by font size/boldness
    - Handles multi-column layouts (basic support)
    - Cleans common PDF text artifacts
    """

    # Minimum font size ratio relative to body text to consider a heading
    HEADING_FONT_SIZE_MULTIPLIER = 1.15

    # Regex patterns for IS standard clause numbering
    CLAUSE_PATTERN = re.compile(
        r"^\s*(\d+(?:\.\d+)*)\s+([A-Z][^.\n]{3,80})\s*$",
        re.MULTILINE,
    )

    def __init__(self) -> None:
        pass

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def extract_pdf(
        self,
        pdf_path: Path,
        page_numbers: Optional[list[int]] = None,
    ) -> TextExtractionResult:
        """
        Extract text from an entire PDF or specific pages.

        Args:
            pdf_path: Path to the PDF file.
            page_numbers: 1-indexed list of pages to extract.
                          None = extract all pages.

        Returns:
            TextExtractionResult
        """
        try:
            import fitz
        except ImportError as exc:
            raise ImportError("PyMuPDF required: pip install pymupdf") from exc

        pdf_path = Path(pdf_path)
        doc = fitz.open(str(pdf_path))
        total_pages = len(doc)

        extracted_pages: list[ExtractedPage] = []
        all_text_parts: list[str] = []

        target_pages = set(page_numbers) if page_numbers else set(range(1, total_pages + 1))

        logger.info("Extracting text from %s (%d pages)", pdf_path.name, total_pages)

        with doc:
            # First pass: compute median font size for heading detection
            font_sizes = self._collect_font_sizes(doc, target_pages)
            median_font = self._median(font_sizes) if font_sizes else 10.0

            for page_idx in range(total_pages):
                page_number = page_idx + 1
                if page_number not in target_pages:
                    continue

                page = doc[page_idx]
                extracted = self._extract_page(page, page_number, median_font)
                extracted_pages.append(extracted)
                if extracted.raw_text:
                    all_text_parts.append(extracted.raw_text)

        full_text = "\n\n".join(all_text_parts)

        logger.info(
            "Text extraction complete: %d pages, %d chars",
            len(extracted_pages), len(full_text),
        )

        return TextExtractionResult(
            pdf_name=pdf_path.name,
            total_pages=total_pages,
            pages=extracted_pages,
            full_text=full_text,
        )

    def extract_page_text(self, pdf_path: Path, page_number: int) -> Optional[ExtractedPage]:
        """Extract text from a single page (1-indexed)."""
        result = self.extract_pdf(pdf_path, page_numbers=[page_number])
        return result.get_page(page_number)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _extract_page(
        self,
        page: "fitz.Page",
        page_number: int,
        median_font_size: float,
    ) -> ExtractedPage:
        """Extract structured text blocks from a single page."""
        import fitz

        rect = page.rect
        blocks_raw = page.get_text("dict", sort=True)["blocks"]

        extracted_blocks: list[ExtractedBlock] = []
        text_parts: list[str] = []
        block_id = 0

        for raw_block in blocks_raw:
            if raw_block.get("type") != 0:  # type 0 = text block
                continue

            block_text_parts: list[str] = []
            max_font_size = 0.0
            is_bold = False

            for line in raw_block.get("lines", []):
                for span in line.get("spans", []):
                    span_text = span.get("text", "").strip()
                    if not span_text:
                        continue
                    block_text_parts.append(span_text)
                    fs = span.get("size", 0.0)
                    if fs > max_font_size:
                        max_font_size = fs
                    flags = span.get("flags", 0)
                    if flags & 16:  # bold flag in PyMuPDF
                        is_bold = True

            block_text = " ".join(block_text_parts).strip()
            if not block_text:
                continue

            bbox = raw_block.get("bbox", (0, 0, 0, 0))

            is_heading = (
                max_font_size >= median_font_size * self.HEADING_FONT_SIZE_MULTIPLIER
                or is_bold
            ) and len(block_text) < 120

            eb = ExtractedBlock(
                block_id=block_id,
                page_number=page_number,
                text=block_text,
                bbox=tuple(bbox),
                font_size=round(max_font_size, 1),
                is_bold=is_bold,
                is_heading_candidate=is_heading,
            )
            extracted_blocks.append(eb)
            text_parts.append(block_text)
            block_id += 1

        raw_text = "\n".join(text_parts)

        return ExtractedPage(
            page_number=page_number,
            width=round(rect.width, 2),
            height=round(rect.height, 2),
            raw_text=raw_text,
            blocks=extracted_blocks,
            has_text=bool(raw_text.strip()),
        )

    def _collect_font_sizes(
        self,
        doc: "fitz.Document",
        target_pages: set[int],
    ) -> list[float]:
        """Collect all font sizes across target pages for median computation."""
        sizes: list[float] = []
        for page_idx in range(len(doc)):
            if (page_idx + 1) not in target_pages:
                continue
            page = doc[page_idx]
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        fs = span.get("size", 0.0)
                        if fs > 0:
                            sizes.append(fs)
        return sizes

    @staticmethod
    def _median(values: list[float]) -> float:
        """Compute median of a list of floats."""
        if not values:
            return 10.0
        sorted_vals = sorted(values)
        mid = len(sorted_vals) // 2
        if len(sorted_vals) % 2 == 0:
            return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
        return sorted_vals[mid]


# =============================================================================
# Convenience function
# =============================================================================

def extract_text(pdf_path: Path, page_numbers: Optional[list[int]] = None) -> TextExtractionResult:
    """
    Convenience wrapper: extract text from a PDF.

    Args:
        pdf_path: Path to the PDF.
        page_numbers: Optional list of 1-indexed page numbers to extract.
                      None = extract all pages.

    Returns:
        TextExtractionResult
    """
    extractor = TextExtractor()
    return extractor.extract_pdf(Path(pdf_path), page_numbers=page_numbers)
