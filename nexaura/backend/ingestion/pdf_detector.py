"""
pdf_detector.py — Phase 1: PDF Analysis and Classification

Project: Nexaura (SIH 2026 — SIH26107)

Uses PyMuPDF to inspect PDFs before any Gemini API call.
Classifies each PDF and each page to determine the optimal
processing strategy (direct text extraction vs Gemini OCR).

This module costs ZERO API calls. It runs entirely locally.

Outputs:
    PDFPageInfo      — per-page analysis result
    PDFAnalysisResult — per-document classification
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import xxhash

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class PDFType(str, Enum):
    """Classification of the PDF document as a whole."""
    TEXT_PDF   = "text_pdf"    # All or majority pages have native text layer
    SCANNED_PDF= "scanned_pdf" # All or majority pages are scanned images
    MIXED_PDF  = "mixed_pdf"   # Some pages are text, some are scanned
    INVALID_PDF= "invalid_pdf" # Cannot be opened or is corrupt


class PageType(str, Enum):
    """Classification of an individual page."""
    TEXT_PAGE    = "text_page"    # Has reliable text layer — use text_extractor
    SCANNED_PAGE = "scanned_page" # Image-only — must use Gemini
    MIXED_PAGE   = "mixed_page"   # Has both text and images — Gemini preferred
    BLANK_PAGE   = "blank_page"   # Near-empty page — skip or mark


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class PDFPageInfo:
    """Analysis result for a single PDF page."""

    page_number: int           # 1-indexed
    page_type: PageType
    has_text_layer: bool
    text_length: int           # number of characters extracted by PyMuPDF
    image_count: int           # number of image objects on this page
    width: float               # page width in points
    height: float              # page height in points
    requires_gemini: bool      # True if Gemini should process this page
    text_preview: str = ""     # First 200 chars of extracted text (for debug)
    page_hash: str = ""        # xxhash of page content (for caching)


@dataclass
class PDFAnalysisResult:
    """Complete analysis result for a PDF document."""

    pdf_path: Path
    pdf_name: str
    file_hash: str             # xxhash of the entire PDF file
    file_size_bytes: int
    total_pages: int

    pdf_type: PDFType
    is_valid: bool

    pages: list[PDFPageInfo] = field(default_factory=list)

    # Summary counts
    text_pages: int = 0
    scanned_pages: int = 0
    mixed_pages: int = 0
    blank_pages: int = 0
    pages_requiring_gemini: int = 0

    # Error if invalid
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        """Compute summary counts from page list."""
        for p in self.pages:
            if p.page_type == PageType.TEXT_PAGE:
                self.text_pages += 1
            elif p.page_type == PageType.SCANNED_PAGE:
                self.scanned_pages += 1
            elif p.page_type == PageType.MIXED_PAGE:
                self.mixed_pages += 1
            elif p.page_type == PageType.BLANK_PAGE:
                self.blank_pages += 1
            if p.requires_gemini:
                self.pages_requiring_gemini += 1


# =============================================================================
# Core Detector
# =============================================================================

class PDFDetector:
    """
    Analyses BIS PDF documents using PyMuPDF to determine:

    1. Whether the PDF is valid and readable
    2. Per-page classification (text / scanned / mixed / blank)
    3. Which pages require Gemini Flash processing vs. direct text extraction
    4. File and page hashes for deduplication and caching

    No Gemini API calls are made by this module.
    """

    def __init__(
        self,
        text_threshold: int = 50,
        force_gemini: bool = False,
        blank_threshold: int = 10,
    ) -> None:
        """
        Args:
            text_threshold: Minimum character count to consider a page as
                having a reliable text layer. Pages below this are sent to
                Gemini. Default: 50.
            force_gemini: If True, mark ALL pages as requiring Gemini
                regardless of text layer. Useful for quality validation.
                WARNING: significantly increases API usage.
            blank_threshold: Character count below which a page is classified
                as blank.
        """
        self.text_threshold = text_threshold
        self.force_gemini = force_gemini
        self.blank_threshold = blank_threshold

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def analyse(self, pdf_path: Path) -> PDFAnalysisResult:
        """
        Analyse a single PDF file.

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            PDFAnalysisResult with per-page breakdowns.

        Raises:
            No exceptions are raised — invalid PDFs return an error result.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError as e:
            raise ImportError(
                "PyMuPDF is required. Install with: pip install pymupdf"
            ) from e

        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            logger.error("PDF not found: %s", pdf_path)
            return PDFAnalysisResult(
                pdf_path=pdf_path,
                pdf_name=pdf_path.name,
                file_hash="",
                file_size_bytes=0,
                total_pages=0,
                pdf_type=PDFType.INVALID_PDF,
                is_valid=False,
                error_message=f"File not found: {pdf_path}",
            )

        file_size = pdf_path.stat().st_size
        file_hash = self._hash_file(pdf_path)

        try:
            doc = fitz.open(str(pdf_path))
        except Exception as exc:
            logger.error("Cannot open PDF %s: %s", pdf_path.name, exc)
            return PDFAnalysisResult(
                pdf_path=pdf_path,
                pdf_name=pdf_path.name,
                file_hash=file_hash,
                file_size_bytes=file_size,
                total_pages=0,
                pdf_type=PDFType.INVALID_PDF,
                is_valid=False,
                error_message=str(exc),
            )

        pages: list[PDFPageInfo] = []

        with doc:
            total_pages = len(doc)
            logger.info(
                "Analysing %s (%d pages, %.1f KB)",
                pdf_path.name, total_pages, file_size / 1024,
            )

            for page_idx in range(total_pages):
                page = doc[page_idx]
                page_info = self._analyse_page(page, page_idx + 1)
                pages.append(page_info)
                logger.debug(
                    "  Page %d: %s | text=%d chars | images=%d | gemini=%s",
                    page_info.page_number,
                    page_info.page_type.value,
                    page_info.text_length,
                    page_info.image_count,
                    page_info.requires_gemini,
                )

        pdf_type = self._classify_pdf(pages, total_pages)

        result = PDFAnalysisResult(
            pdf_path=pdf_path,
            pdf_name=pdf_path.name,
            file_hash=file_hash,
            file_size_bytes=file_size,
            total_pages=total_pages,
            pdf_type=pdf_type,
            is_valid=True,
            pages=pages,
        )

        logger.info(
            "%s → %s | text=%d scanned=%d mixed=%d blank=%d gemini_needed=%d",
            pdf_path.name, pdf_type.value,
            result.text_pages, result.scanned_pages,
            result.mixed_pages, result.blank_pages,
            result.pages_requiring_gemini,
        )
        return result

    def analyse_directory(self, directory: Path) -> list[PDFAnalysisResult]:
        """
        Recursively analyse all PDFs in a directory.

        Args:
            directory: Root directory to scan for PDFs.

        Returns:
            List of PDFAnalysisResult, one per PDF found.
        """
        directory = Path(directory)
        pdf_files = sorted(directory.rglob("*.pdf"))

        if not pdf_files:
            logger.warning("No PDF files found in %s", directory)
            return []

        logger.info("Found %d PDF files in %s", len(pdf_files), directory)
        results = []
        for pdf_path in pdf_files:
            result = self.analyse(pdf_path)
            results.append(result)
        return results

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _analyse_page(self, page: "fitz.Page", page_number: int) -> PDFPageInfo:
        """Analyse a single page and return PDFPageInfo."""
        import fitz

        rect = page.rect
        width, height = rect.width, rect.height

        # Extract text via PyMuPDF
        text = page.get_text("text").strip()
        text_length = len(text)

        # Count embedded images
        image_list = page.get_images(full=False)
        image_count = len(image_list)

        # Determine page type
        is_blank = text_length <= self.blank_threshold and image_count == 0

        if is_blank:
            page_type = PageType.BLANK_PAGE
            requires_gemini = False

        elif self.force_gemini:
            page_type = PageType.MIXED_PAGE
            requires_gemini = True

        elif text_length >= self.text_threshold and image_count == 0:
            # Clean text page — no images, enough text
            page_type = PageType.TEXT_PAGE
            requires_gemini = False

        elif text_length >= self.text_threshold and image_count > 0:
            # Has text AND images — might be mixed layout (text + diagrams/tables)
            # Still prefer Gemini for full structural understanding
            page_type = PageType.MIXED_PAGE
            requires_gemini = True

        elif text_length < self.text_threshold and image_count > 0:
            # Scanned image page — definitely needs Gemini
            page_type = PageType.SCANNED_PAGE
            requires_gemini = True

        else:
            # Edge case: very little text, no images
            page_type = PageType.BLANK_PAGE
            requires_gemini = False

        # Hash page content for caching
        page_content = f"{page_number}:{text[:500]}:{image_count}"
        page_hash = xxhash.xxh64(page_content.encode()).hexdigest()

        return PDFPageInfo(
            page_number=page_number,
            page_type=page_type,
            has_text_layer=text_length >= self.text_threshold,
            text_length=text_length,
            image_count=image_count,
            width=round(width, 2),
            height=round(height, 2),
            requires_gemini=requires_gemini,
            text_preview=text[:200],
            page_hash=page_hash,
        )

    def _classify_pdf(self, pages: list[PDFPageInfo], total: int) -> PDFType:
        """Determine overall PDF type based on page classifications."""
        if total == 0:
            return PDFType.INVALID_PDF

        non_blank = [p for p in pages if p.page_type != PageType.BLANK_PAGE]
        if not non_blank:
            return PDFType.INVALID_PDF

        text_count    = sum(1 for p in non_blank if p.page_type == PageType.TEXT_PAGE)
        scanned_count = sum(1 for p in non_blank if p.page_type == PageType.SCANNED_PAGE)
        mixed_count   = sum(1 for p in non_blank if p.page_type == PageType.MIXED_PAGE)
        total_non_blank = len(non_blank)

        text_ratio    = text_count    / total_non_blank
        scanned_ratio = scanned_count / total_non_blank

        if text_ratio >= 0.85:
            return PDFType.TEXT_PDF
        elif scanned_ratio >= 0.85:
            return PDFType.SCANNED_PDF
        else:
            return PDFType.MIXED_PDF

    @staticmethod
    def _hash_file(path: Path) -> str:
        """Compute xxhash of a file in streaming chunks."""
        h = xxhash.xxh64()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()


# =============================================================================
# Convenience function
# =============================================================================

def analyse_pdf(
    pdf_path: Path,
    text_threshold: int = 50,
    force_gemini: bool = False,
) -> PDFAnalysisResult:
    """
    Convenience wrapper: analyse a single PDF.

    Args:
        pdf_path: Path to the PDF file.
        text_threshold: Minimum chars to consider a page as text.
        force_gemini: Send all pages to Gemini.

    Returns:
        PDFAnalysisResult
    """
    detector = PDFDetector(
        text_threshold=text_threshold,
        force_gemini=force_gemini,
    )
    return detector.analyse(Path(pdf_path))
