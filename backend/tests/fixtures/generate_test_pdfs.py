"""
Generates SYNTHETIC TEST-ONLY PDFs for exercising the ingestion pipeline.

These are NOT real BIS documents. Every generated file has "SYNTHETIC TEST
DOCUMENT — NOT AN OFFICIAL BIS STANDARD" stamped directly into its text, and
they live under tests/fixtures/, never under data/raw/, so they cannot be
mistaken for real ingested content. Run this once to (re)generate the
fixture files used by tests/test_ingestion.py.
"""

from pathlib import Path

import pymupdf

FIXTURES_DIR = Path(__file__).parent

DISCLAIMER = "SYNTHETIC TEST DOCUMENT -- NOT AN OFFICIAL BIS STANDARD -- FOR PIPELINE TESTING ONLY"


def make_text_pdf(path: Path) -> None:
    """A PDF with a normal, extractable text layer (the 'native text' case)."""
    doc = pymupdf.open()
    page = doc.new_page()
    text = (
        f"{DISCLAIMER}\n\n"
        "IS 99999\n"
        "Synthetic Specification for Pipeline Testing\n\n"
        "First Revision\n\n"
        "1 SCOPE\n"
        "This synthetic document exists only to test the ingestion pipeline.\n\n"
        "2 REFERENCES\n"
        "This document references IS 302-1 as an example of a standard-number mention.\n\n"
        "3 REQUIREMENTS\n"
        "No real requirements are specified in this test document.\n"
    )
    page.insert_text((50, 50), text, fontsize=11)
    doc.save(str(path))
    doc.close()


def make_scanned_pdf(path: Path) -> None:
    """A PDF with no text layer at all — a blank/graphics-only page with
    text burned into an image, simulating a scanned page that requires OCR."""
    doc = pymupdf.open()
    page = doc.new_page()
    # Draw the disclaimer and content as vector text converted to a raster
    # image, so the PDF's text layer is empty and OCR is required.
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 600, 300))
    pix.set_rect(pix.irect, (255, 255, 255))
    tmp_doc = pymupdf.open()
    tmp_page = tmp_doc.new_page(width=600, height=300)
    tmp_page.insert_text((20, 40), DISCLAIMER, fontsize=10)
    tmp_page.insert_text((20, 80), "IS 88888", fontsize=14)
    tmp_page.insert_text((20, 110), "Synthetic Scanned-Style Test Document", fontsize=12)
    tmp_pix = tmp_page.get_pixmap(dpi=150)
    img_bytes = tmp_pix.tobytes("png")
    tmp_doc.close()

    page.insert_image(pymupdf.Rect(0, 0, 600, 300), stream=img_bytes)
    doc.save(str(path))
    doc.close()


def make_mixed_pdf(path: Path) -> None:
    """Page 1 has native text; page 2 is image-only (requires OCR)."""
    doc = pymupdf.open()

    page1 = doc.new_page()
    page1.insert_text(
        (50, 50),
        f"{DISCLAIMER}\n\nIS 77777\nMixed Test Document, Page 1 (native text)\n\n1 SCOPE\nNative text page.",
        fontsize=11,
    )

    tmp_doc = pymupdf.open()
    tmp_page = tmp_doc.new_page(width=600, height=300)
    tmp_page.insert_text((20, 40), DISCLAIMER, fontsize=10)
    tmp_page.insert_text((20, 80), "Page 2 (image only, requires OCR)", fontsize=12)
    tmp_pix = tmp_page.get_pixmap(dpi=150)
    img_bytes = tmp_pix.tobytes("png")
    tmp_doc.close()

    page2 = doc.new_page()
    page2.insert_image(pymupdf.Rect(0, 0, 600, 300), stream=img_bytes)

    doc.save(str(path))
    doc.close()


def make_empty_pdf(path: Path) -> None:
    """A valid single-page PDF with no text and no image content at all —
    tests the case where OCR runs but finds nothing meaningful to extract."""
    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()


def make_invalid_file(path: Path) -> None:
    """Not a PDF at all — for validation testing."""
    path.write_bytes(b"this is not a pdf file")


def make_table_pdf(path: Path) -> None:
    """A PDF with native text plus a hand-drawn grid table (Phase 8) —
    exercises PyMuPDF's find_tables() detection and the [TABLE]...[/TABLE]
    preservation in app/ingestion/extraction.py, and includes a
    publication-year-shaped 4-digit number for metadata extraction."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (50, 50),
        f"{DISCLAIMER}\n\nIS 66666 : 2021\nSynthetic Table Test Document\n\nSecond Revision\n\n"
        "1 SCOPE\nSee the table below for dimensional tolerances.",
        fontsize=11,
    )

    x0, y0 = 50, 200
    col_w, row_h = 100, 20
    for r in range(3):
        page.draw_line((x0, y0 + r * row_h), (x0 + 3 * col_w, y0 + r * row_h))
    for c in range(4):
        page.draw_line((x0 + c * col_w, y0), (x0 + c * col_w, y0 + 2 * row_h))

    headers = ["Size", "Tolerance", "Grade"]
    rows = [["10mm", "+/-0.5", "A"]]
    for c, h in enumerate(headers):
        page.insert_text((x0 + c * col_w + 5, y0 + 15), h, fontsize=9)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            page.insert_text((x0 + c * col_w + 5, y0 + (r + 2) * row_h - 5), val, fontsize=9)

    doc.save(str(path))
    doc.close()


if __name__ == "__main__":
    make_text_pdf(FIXTURES_DIR / "test_text.pdf")
    make_scanned_pdf(FIXTURES_DIR / "test_scanned.pdf")
    make_mixed_pdf(FIXTURES_DIR / "test_mixed.pdf")
    make_empty_pdf(FIXTURES_DIR / "test_empty.pdf")
    make_invalid_file(FIXTURES_DIR / "test_invalid.txt")
    make_table_pdf(FIXTURES_DIR / "test_table.pdf")
    print("Generated synthetic test fixtures in", FIXTURES_DIR)
