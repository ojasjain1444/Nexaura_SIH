from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    original_filename: str
    status: str
    # Phase 9: a small, frontend-facing summary of `status` — one of
    # "PROCESSING" / "INDEXED" / "FAILED". See
    # app/services/document_service.py's _display_status() for exactly how
    # it's derived (in particular: "completed" alone does not mean
    # "INDEXED" — chunk_count must also be > 0).
    display_status: str
    page_count: int | None
    source_type: str
    # Phase 12: what KIND of BIS material this is (see
    # app.product.document_type.DocumentType) — kept separate from
    # source_type, which answers whether authenticity has been verified.
    document_type: str
    source: str | None
    source_url: str | None
    acquisition_date: datetime | None
    standard_id: str | None
    extracted_standard_number: str | None
    extracted_title: str | None
    extracted_edition: str | None
    extracted_publication_year: str | None
    chunk_count: int
    file_hash: str
    ingested_at: datetime


class DocumentStatusResponse(BaseModel):
    id: str
    status: str
    error_message: str | None


class DocumentPageResponse(BaseModel):
    page_number: int
    text: str
    extraction_method: str
    ocr_confidence: float | None


class DocumentFeatureResponse(BaseModel):
    feature_type: str
    value: str
    page_number: int
    section: str | None
