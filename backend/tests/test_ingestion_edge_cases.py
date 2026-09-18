"""
Additional edge-case tests for the ingestion pipeline: large documents and
partial-metadata documents. Uses synthetic, generated-in-memory PDFs (never
real BIS content).
"""

import io

import pymupdf

from app.services.document_service import DocumentService


def _build_pdf_bytes(pages_text: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_text((50, 50), text, fontsize=10)
    buffer = io.BytesIO()
    doc.save(buffer)
    doc.close()
    return buffer.getvalue()


def test_large_document_processes_all_pages(db_session, isolated_storage):
    """50 pages is small in absolute terms but large relative to every
    other fixture in this suite (1-2 pages) — enough to prove the
    page-by-page loop in extract_pdf_pages doesn't break or truncate on a
    document larger than the trivial single-page case."""
    page_texts = [f"SYNTHETIC TEST DOCUMENT -- NOT AN OFFICIAL BIS STANDARD\nPage {i} content." for i in range(1, 51)]
    content = _build_pdf_bytes(page_texts)

    service = DocumentService(db_session)
    document = service.register_upload(content, "large_test.pdf", "application/pdf", source_type="test")
    result = service.process_document(document.id, content)

    assert result.status == "completed"
    assert result.page_count == 50
    pages = service.get_pages(document.id)
    assert len(pages) == 50
    assert pages[49].text.strip().endswith("Page 50 content.")


def test_document_with_no_recognizable_metadata_leaves_fields_null(db_session, isolated_storage):
    """A document whose text doesn't match any BIS numbering/edition
    pattern at all — the extractor must not guess a plausible-looking
    fallback value."""
    content = _build_pdf_bytes(["SYNTHETIC TEST DOCUMENT -- NOT AN OFFICIAL BIS STANDARD\nJust some unrelated prose with no standard number or edition mentioned anywhere."])

    service = DocumentService(db_session)
    document = service.register_upload(content, "no_metadata.pdf", "application/pdf", source_type="test")
    result = service.process_document(document.id, content)

    assert result.status == "completed"
    assert result.extracted_standard_number is None
    assert result.extracted_edition is None
