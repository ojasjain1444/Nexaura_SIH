"""
Document service — orchestrates upload registration and triggers the
ingestion pipeline. This is the single entry point used by both the API
(POST /api/documents/upload) and the CLI (app.ingestion.ingest), so the two
never diverge in behavior.

Phase 9 adds document-management operations (list, delete) and wires
indexing (app.rag.index_document) into the same background flow the upload
endpoint already runs the extraction pipeline in — so a document uploaded
through the API alone reaches a genuinely retrievable state without a
separate manual CLI step. No new ingestion/indexing logic is introduced
here: this only orchestrates the existing Phase 3/4/8 functions.
"""

import logging
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from datetime import datetime, timezone

from app.ingestion.pipeline import run_pipeline
from app.ingestion.storage import store_document_file
from app.ingestion.validation import DocumentValidationError, compute_file_hash, validate_upload
from app.models.standard_document import StandardDocument
from app.ocr.provider import OCRProvider
from app.ocr.tesseract_provider import TesseractOCRProvider
from app.product.document_type import DEFAULT_DOCUMENT_TYPE, DocumentType
from app.rag.index_document import IndexingError, index_document
from app.rag.keyword_search import delete_document_chunks as delete_keyword_search_chunks
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentFeatureResponse, DocumentPageResponse, DocumentResponse, DocumentStatusResponse

VALID_DOCUMENT_TYPES = {t.value for t in DocumentType}


class InvalidDocumentTypeError(Exception):
    pass

logger = logging.getLogger("bis_sahayak")

# Display status shown to the frontend — a small, honest summary of the
# underlying pipeline state machine (app/ingestion/pipeline.py), which has
# more granular internal stages than a document-management UI needs.
# "INDEXED" is never inferred from `status` alone: a document can reach
# pipeline status "completed" and still have zero chunks (indexing not yet
# run, or it produced no extractable chunks) — see chunk_count below.
DISPLAY_STATUS_PROCESSING = "PROCESSING"
DISPLAY_STATUS_INDEXED = "INDEXED"
DISPLAY_STATUS_FAILED = "FAILED"


def _display_status(document: StandardDocument, chunk_count: int) -> str:
    if document.status == "failed":
        return DISPLAY_STATUS_FAILED
    if document.status == "completed" and chunk_count > 0:
        return DISPLAY_STATUS_INDEXED
    return DISPLAY_STATUS_PROCESSING


class DuplicateDocumentError(Exception):
    def __init__(self, existing_document_id: str):
        self.existing_document_id = existing_document_id
        super().__init__(f"Document already exists as {existing_document_id}")


def _to_response(document: StandardDocument, chunk_count: int = 0) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        original_filename=document.original_filename,
        status=document.status,
        display_status=_display_status(document, chunk_count),
        page_count=document.page_count,
        source_type=document.source_type,
        document_type=document.document_type,
        source=document.source,
        source_url=document.source_url,
        acquisition_date=document.acquisition_date,
        standard_id=document.standard_id,
        extracted_standard_number=document.extracted_standard_number,
        extracted_title=document.extracted_title,
        extracted_edition=document.extracted_edition,
        extracted_publication_year=document.extracted_publication_year,
        chunk_count=chunk_count,
        file_hash=document.file_hash,
        ingested_at=document.ingested_at,
    )


class DocumentService:
    def __init__(self, db: Session, ocr_provider: OCRProvider | None = None):
        self.db = db
        self.repo = DocumentRepository(db)
        self.ocr_provider = ocr_provider or TesseractOCRProvider()

    def register_upload(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
        source_type: str = "unverified",
        document_type: str | None = None,
        source: str | None = None,
    ) -> DocumentResponse:
        validate_upload(content, mime_type, filename)

        # Phase 12: document_type is an explicit, user-asserted
        # classification — never inferred by the pipeline. An unrecognized
        # value is rejected rather than silently coerced, matching how
        # language/mode validation works elsewhere in this project (see
        # app/schemas/chat.py). Omitted -> defaults to OTHER, never guessed.
        resolved_document_type = document_type or DEFAULT_DOCUMENT_TYPE
        if resolved_document_type not in VALID_DOCUMENT_TYPES:
            supported = ", ".join(sorted(VALID_DOCUMENT_TYPES))
            raise InvalidDocumentTypeError(f"Unsupported document_type '{document_type}'. Supported: {supported}")

        file_hash = compute_file_hash(content)
        existing = self.repo.get_by_hash(file_hash)
        if existing is not None:
            raise DuplicateDocumentError(existing.id)

        document_id = str(uuid.uuid4())
        storage_path = store_document_file(document_id, content)

        document = StandardDocument(
            id=document_id,
            original_filename=filename,
            file_hash=file_hash,
            mime_type=mime_type,
            size_bytes=len(content),
            storage_path=storage_path,
            status="uploaded",
            source_type=source_type,
            document_type=resolved_document_type,
            source=source,
            # acquisition_date defaults to "now" — the moment this system
            # received the file. This is honest for a direct upload (no
            # separate real-world acquisition step exists yet); a future
            # batch-import path could set it independently to reflect when
            # the file was actually obtained, if that ever differs.
            acquisition_date=datetime.now(timezone.utc),
        )
        self.repo.create(document)
        return _to_response(document)

    def process_document(self, document_id: str, content: bytes) -> DocumentResponse:
        document = run_pipeline(self.db, document_id, content, self.ocr_provider)

        if document.status == "completed":
            # Phase 9: indexing used to be a separate manual CLI step
            # (app.rag.index_document_cli / app.ingestion.ingest_and_index).
            # Running it here means POST /api/documents/upload alone takes
            # a document all the way to retrievable — matching the target
            # flow — without changing index_document() itself. A failure
            # here does not revert the pipeline's "completed" status (text
            # extraction genuinely succeeded); it only means the document
            # stays un-indexed, reported honestly via chunk_count == 0 /
            # display_status "PROCESSING", not silently hidden.
            try:
                index_document(self.db, document_id)
            except IndexingError as exc:
                logger.warning("Auto-indexing failed for document %s: %s", document_id, exc)

        chunk_count = self.repo.count_chunks(document_id)
        return _to_response(document, chunk_count)

    def get_status(self, document_id: str) -> DocumentStatusResponse | None:
        document = self.repo.get_by_id(document_id)
        if document is None:
            return None
        return DocumentStatusResponse(id=document.id, status=document.status, error_message=document.error_message)

    def get_document(self, document_id: str) -> DocumentResponse | None:
        document = self.repo.get_by_id(document_id)
        if document is None:
            return None
        return _to_response(document, self.repo.count_chunks(document_id))

    def list_documents(self) -> list[DocumentResponse]:
        return [_to_response(doc, self.repo.count_chunks(doc.id)) for doc in self.repo.list_all()]

    def reindex_document(self, document_id: str) -> DocumentResponse | None:
        document = self.repo.get_by_id(document_id)
        if document is None:
            return None
        if document.status != "completed":
            raise IndexingError(
                f"Document {document_id} has status '{document.status}', not 'completed'. "
                "Only fully-processed documents can be (re)indexed."
            )
        index_document(self.db, document_id)
        return _to_response(document, self.repo.count_chunks(document_id))

    def delete_document(self, document_id: str) -> bool:
        document = self.repo.get_by_id(document_id)
        if document is None:
            return False

        # Best-effort file removal: a missing/already-gone file must not
        # block deleting the (still-real) database record.
        try:
            Path(document.storage_path).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not remove stored file for document %s: %s", document_id, exc)

        delete_keyword_search_chunks(self.db, document_id)  # Phase 10 FTS5 index — kept in sync, not cascaded by the ORM
        self.repo.delete(document)  # cascades to pages/features/chunks
        return True

    def get_pages(self, document_id: str) -> list[DocumentPageResponse] | None:
        document = self.repo.get_with_pages(document_id)
        if document is None:
            return None
        return [
            DocumentPageResponse(
                page_number=p.page_number,
                text=p.text,
                extraction_method=p.extraction_method,
                ocr_confidence=p.ocr_confidence,
            )
            for p in document.pages
        ]

    def get_features(self, document_id: str) -> list[DocumentFeatureResponse] | None:
        document = self.repo.get_with_features(document_id)
        if document is None:
            return None
        return [
            DocumentFeatureResponse(
                feature_type=f.feature_type, value=f.value, page_number=f.page_number, section=f.section
            )
            for f in document.features
        ]
