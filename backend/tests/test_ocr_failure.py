"""
OCR failure handling: verifies the pipeline marks a document 'failed' with
a real error message when the OCR provider itself raises, rather than
silently producing empty/fabricated text.
"""

import io

import pymupdf
import pytest
from PIL import Image

from app.ocr.provider import OCRResult
from app.services.document_service import DocumentService


class AlwaysFailingOCRProvider:
    def extract_text(self, image: Image.Image) -> OCRResult:
        raise RuntimeError("Simulated OCR engine failure for testing")


def _build_image_only_pdf() -> bytes:
    doc = pymupdf.open()
    tmp_doc = pymupdf.open()
    tmp_page = tmp_doc.new_page(width=300, height=150)
    tmp_page.insert_text((10, 30), "SYNTHETIC TEST DOCUMENT -- image only", fontsize=10)
    tmp_pix = tmp_page.get_pixmap(dpi=100)
    img_bytes = tmp_pix.tobytes("png")
    tmp_doc.close()

    page = doc.new_page()
    page.insert_image(pymupdf.Rect(0, 0, 300, 150), stream=img_bytes)
    buffer = io.BytesIO()
    doc.save(buffer)
    doc.close()
    return buffer.getvalue()


def test_ocr_provider_failure_marks_document_failed(db_session, isolated_storage):
    content = _build_image_only_pdf()
    service = DocumentService(db_session, ocr_provider=AlwaysFailingOCRProvider())
    document = service.register_upload(content, "ocr_fail_test.pdf", "application/pdf", source_type="test")

    result = service.process_document(document.id, content)

    assert result.status == "failed"
    status = service.get_status(document.id)
    assert "Simulated OCR engine failure" in status.error_message
