"""
Document ingestion pipeline orchestrator.

Input document → validation → registration → text extraction (native/OCR
per page) → metadata extraction → feature extraction → storage.

Each stage updates `StandardDocument.status` as it completes, so a caller
polling GET /api/documents/{id}/status sees genuine progress, not a single
jump from "uploaded" to "completed". If any stage raises, the document is
marked "failed" with the real error message (not swallowed, not silently
retried) — per Step 9's requirement to never expose a document as
successfully processed until the pipeline actually reaches completion.
"""

import logging

from sqlalchemy.orm import Session

from app.ingestion.extraction import PdfExtractionError, extract_pdf_pages
from app.ingestion.feature_extraction import extract_features_from_page
from app.ingestion.metadata_extraction import extract_metadata
from app.ingestion.scope_requirement_extraction import SCOPE_SEARCH_PAGE_WINDOW, extract_requirements, extract_scope
from app.models.document_feature import DocumentFeature
from app.models.document_page import DocumentPage
from app.models.standard_document import StandardDocument
from app.models.standard_requirement import StandardRequirement
from app.models.standard_scope import StandardScope
from app.ocr.provider import OCRProvider
from app.repositories.document_repository import DocumentRepository

logger = logging.getLogger("bis_sahayak")


class PipelineError(Exception):
    pass


def run_pipeline(db: Session, document_id: str, pdf_bytes: bytes, ocr_provider: OCRProvider) -> StandardDocument:
    repo = DocumentRepository(db)
    document = repo.get_by_id(document_id)
    if document is None:
        raise PipelineError(f"Document {document_id} not found")

    try:
        repo.update_status(document, "processing")

        # --- Text extraction (native or OCR, per page) ---
        try:
            page_results = extract_pdf_pages(pdf_bytes, ocr_provider)
        except PdfExtractionError as exc:
            repo.update_status(document, "failed", error_message=f"Text extraction failed: {exc}")
            return document

        repo.set_page_count(document, len(page_results))
        for page_result in page_results:
            repo.add_page(
                DocumentPage(
                    document_id=document.id,
                    page_number=page_result.page_number,
                    text=page_result.text,
                    extraction_method=page_result.extraction_method,
                    ocr_confidence=page_result.ocr_confidence,
                )
            )
        repo.update_status(document, "text_extracted")

        # --- Metadata extraction ---
        try:
            # The real cover page is not always page 1: real BIS PDFs
            # commonly place a "Disclosure to Promote the Right To
            # Information" notice (and sometimes a blank page) before it
            # — confirmed across multiple genuine standards. Looking at
            # the first several pages, not just page 1, lets
            # extract_metadata find the actual cover page's title/number.
            leading_pages_text = "\n".join(p.text for p in page_results[:6])
            metadata = extract_metadata(leading_pages_text)
            repo.set_extracted_metadata(
                document, metadata.standard_number, metadata.title, metadata.edition, metadata.publication_year
            )
        except Exception as exc:
            # Metadata extraction failing should not fail the whole
            # document — it degrades to "no metadata extracted", which is
            # represented honestly via the null fields already set.
            logger.warning("Metadata extraction failed for document %s: %s", document.id, exc)

        # --- Feature extraction (per page) ---
        try:
            for page_result in page_results:
                features = extract_features_from_page(page_result.text, page_result.page_number)
                for feature in features:
                    repo.add_feature(
                        DocumentFeature(
                            document_id=document.id,
                            feature_type=feature.feature_type,
                            value=feature.value,
                            page_number=feature.page_number,
                            section=feature.section,
                        )
                    )
            repo.update_status(document, "features_extracted")
        except Exception as exc:
            repo.update_status(document, "failed", error_message=f"Feature extraction failed: {exc}")
            return document

        # --- Scope and requirement extraction (Step 5b) ---
        # Same "degrade, don't fail" handling as metadata extraction above:
        # a document with no detectable SCOPE clause or no obligation
        # clauses is still a genuinely usable document (it just has fewer
        # rows in these tables), so a failure here must never turn a
        # successfully-extracted document into a "failed" one.
        try:
            all_pages = [(p.page_number, p.text) for p in page_results]
            scope = extract_scope(all_pages[:SCOPE_SEARCH_PAGE_WINDOW])
            if scope is not None:
                repo.set_scope(
                    StandardScope(
                        document_id=document.id,
                        scope_text=scope.scope_text,
                        page_number=scope.page_number,
                    )
                )

            requirements = extract_requirements(all_pages, own_standard_number=document.extracted_standard_number)
            for requirement in requirements:
                repo.add_requirement(
                    StandardRequirement(
                        document_id=document.id,
                        category=requirement.category,
                        clause_number=requirement.clause_number,
                        requirement_text=requirement.requirement_text,
                        page_number=requirement.page_number,
                        referenced_standards=(
                            ", ".join(requirement.referenced_standards) if requirement.referenced_standards else None
                        ),
                    )
                )
        except Exception as exc:
            logger.warning("Scope/requirement extraction failed for document %s: %s", document.id, exc)

        repo.update_status(document, "completed")
        return document

    except Exception as exc:  # noqa: BLE001 — pipeline-level catch-all is intentional here
        logger.exception("Unexpected pipeline failure for document %s", document.id)
        repo.update_status(document, "failed", error_message=f"Unexpected error: {exc}")
        return document
