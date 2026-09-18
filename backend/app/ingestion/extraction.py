"""
PDF text extraction — page-by-page, deciding independently for each page
whether its native (embedded) text is usable or whether OCR is required.

This is the mechanism behind Step 6's "do not OCR every page
unnecessarily" and "for mixed PDFs, process page by page": a page's
native/OCR decision never depends on any other page in the same document.

Phase 8: native-text pages also run PyMuPDF's table detector
(page.find_tables()) so a real table (e.g. BIS dimensional tolerances) is
not silently flattened into ordinary prose. A detected table's cell grid is
rendered as a delimited [TABLE]...[/TABLE] block (row cells joined with
" | ") inserted in place of the table's default flattened text, so
downstream chunking/embedding/citation code — which only ever sees plain
page text — keeps working unchanged while a reader (human or LLM) can still
tell rows/columns apart. This is deliberately conservative: OCR'd pages are
not table-detected (Tesseract already returns unstructured text with no
layout coordinates to align a table against), and a page with no detected
table is completely unaffected.
"""

from dataclasses import dataclass

import pymupdf
from PIL import Image

from app.ocr.provider import OCRProvider

# A page with fewer than this many non-whitespace characters of native text
# is treated as having no usable text layer (e.g. a scanned image page with
# only a stray watermark string) and is sent to OCR instead.
MIN_NATIVE_TEXT_CHARS = 10

# Render resolution for OCR — high enough for Tesseract accuracy on a
# typical scanned standard page without producing unreasonably large images.
OCR_RENDER_DPI = 300


def _format_table_block(rows: list[list[str | None]]) -> str:
    lines = [" | ".join(cell.strip() if cell else "" for cell in row) for row in rows]
    return "[TABLE]\n" + "\n".join(lines) + "\n[/TABLE]"


def _replace_tables_with_delimited_blocks(page: "pymupdf.Page", native_text: str) -> str:
    """Detects tables on a native-text page and replaces each table's
    default flattened-prose representation with a clearly delimited
    [TABLE]...[/TABLE] block preserving row/column structure. Falls back to
    the original native_text untouched if no table is detected or detection
    itself fails — table structure is a nice-to-have, never a reason to
    fail or alter extraction of a page that has none."""
    try:
        tables = page.find_tables()
    except Exception:
        return native_text

    if not tables.tables:
        return native_text

    result_text = native_text
    for table in tables.tables:
        try:
            rows = table.extract()
        except Exception:
            continue
        if not rows:
            continue

        # The table's own bounding box, re-extracted as plain text, is what
        # find_tables() detected inside native_text — replacing that exact
        # substring (when still present verbatim) keeps every other part of
        # the page text untouched.
        table_text_region = page.get_textbox(table.bbox).strip()
        if table_text_region and table_text_region in result_text:
            result_text = result_text.replace(table_text_region, _format_table_block(rows), 1)

    return result_text


@dataclass
class PageExtractionResult:
    page_number: int  # 1-indexed, matches how a human would cite "page 12"
    text: str
    extraction_method: str  # "native" or "ocr"
    ocr_confidence: float | None


class PdfExtractionError(Exception):
    pass


def extract_pdf_pages(pdf_bytes: bytes, ocr_provider: OCRProvider) -> list[PageExtractionResult]:
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PdfExtractionError(f"Could not open PDF: {exc}") from exc

    if doc.page_count == 0:
        raise PdfExtractionError("PDF has no pages.")

    results: list[PageExtractionResult] = []
    for page_index in range(doc.page_count):
        page = doc[page_index]
        native_text = page.get_text().strip()

        if len(native_text) >= MIN_NATIVE_TEXT_CHARS:
            text_with_tables = _replace_tables_with_delimited_blocks(page, native_text)
            results.append(
                PageExtractionResult(
                    page_number=page_index + 1,
                    text=text_with_tables,
                    extraction_method="native",
                    ocr_confidence=None,
                )
            )
            continue

        # Native text is insufficient — render the page to an image and OCR it.
        pixmap = page.get_pixmap(dpi=OCR_RENDER_DPI)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        ocr_result = ocr_provider.extract_text(image)
        results.append(
            PageExtractionResult(
                page_number=page_index + 1,
                text=ocr_result.text,
                extraction_method="ocr",
                ocr_confidence=ocr_result.confidence,
            )
        )

    doc.close()
    return results


def get_page_count(pdf_bytes: bytes) -> int:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    count = doc.page_count
    doc.close()
    return count
