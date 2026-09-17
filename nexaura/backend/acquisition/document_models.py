"""
document_models.py — Data Models for BIS Document Acquisition & Inventory System

Project: Nexaura (SIH 2026 — SIH26107)

Defines data structures and enums for:
    - Document Types (A-P categories)
    - Document Metadata & Provenance
    - Document Relationships & Versioning
    - Completeness Audit & Inventory Reports
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    """Categorized BIS Document Types (A-P)."""
    MAIN_STANDARD = "main_standard"
    REVISED_STANDARD = "revised_standard"
    AMENDMENT = "amendment"
    CORRIGENDUM = "corrigendum"
    ADDENDUM = "addendum"
    WITHDRAWN_STANDARD = "withdrawn_standard"
    DRAFT_STANDARD = "draft_standard"
    PRODUCT_MANUAL = "product_manual"
    STI = "scheme_of_testing_and_inspection"
    GUIDELINE = "guideline"
    QCO = "quality_control_order"
    GAZETTE_NOTIFICATION = "gazette_notification"
    CERTIFICATION_SCHEME = "certification_scheme"
    HALLMARKING = "hallmarking"
    MANAGEMENT_SYSTEM = "management_system"
    LABORATORY = "laboratory"
    LICENCE = "licence_certificate"
    COMMITTEE = "committee"
    PRODUCT_CATEGORY = "product_category"
    CIRCULAR_NOTICE = "circular_notice"
    FORM = "form"
    WEB_PAGE = "web_page"
    UNKNOWN = "unknown"


class AccessStatus(str, Enum):
    """Status of document acquisition."""
    DOWNLOADED = "downloaded"
    METADATA_ONLY = "metadata_only"
    NOT_PUBLICLY_AVAILABLE = "not_publicly_available"
    FAILED = "failed"


class ProcessingStatus(str, Enum):
    """Status of PDF ingestion & parsing."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RelationType(str, Enum):
    """Explicit document and domain relationships."""
    HAS_EDITION = "HAS_EDITION"
    HAS_AMENDMENT = "HAS_AMENDMENT"
    HAS_CORRIGENDUM = "HAS_CORRIGENDUM"
    HAS_SUPPLEMENT = "HAS_SUPPLEMENT"
    HAS_PRODUCT_MANUAL = "HAS_PRODUCT_MANUAL"
    HAS_STI = "HAS_STI"
    HAS_GUIDELINE = "HAS_GUIDELINE"
    HAS_NOTIFICATION = "HAS_NOTIFICATION"
    REFERENCES = "REFERENCES"
    RELATED_TO = "RELATED_TO"
    SUPERSEDES = "SUPERSEDES"
    SUPERSEDED_BY = "SUPERSEDED_BY"
    HAS_STANDARD = "HAS_STANDARD"
    HAS_QCO = "HAS_QCO"
    HAS_CERTIFICATION = "HAS_CERTIFICATION"
    USES_SCHEME = "USES_SCHEME"
    APPLIES_TO_PRODUCT = "APPLIES_TO_PRODUCT"
    REQUIRES_STANDARD = "REQUIRES_STANDARD"
    TESTED_BY_LAB = "TESTED_BY_LAB"


class DocumentMetadata(BaseModel):
    """Mandatory metadata schema for every acquired BIS document."""
    document_id: str
    document_type: DocumentType = DocumentType.UNKNOWN
    title: str = "Untitled Document"
    standard_number: str = "unknown"
    edition: Optional[str] = None
    year: Optional[int] = None
    version: Optional[str] = None
    revision: Optional[str] = None
    amendment_number: Optional[str] = None
    publication_date: Optional[str] = None
    effective_date: Optional[str] = None
    status: str = "in_force"

    source_url: Optional[str] = None
    document_url: Optional[str] = None
    source_domain: str = "bis.gov.in"

    mime_type: str = "application/pdf"
    file_size: int = 0

    sha256: Optional[str] = None
    xxhash: Optional[str] = None

    downloaded_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_seen_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    parent_standard_id: Optional[str] = None
    parent_document_id: Optional[str] = None

    access_status: AccessStatus = AccessStatus.DOWNLOADED
    processing_status: ProcessingStatus = ProcessingStatus.PENDING

    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentRelationship(BaseModel):
    """Represents directed relationships between standards, products, schemes, and documents."""
    from_id: str
    to_id: str
    relation_type: RelationType
    source_evidence: str = "document_metadata"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CompletenessAudit(BaseModel):
    """Document completeness coverage report per standard."""
    standard_number: str
    expected_documents: List[str] = Field(default_factory=list)
    discovered_documents: int = 0
    downloaded_documents: int = 0
    failed_documents: int = 0
    metadata_only_documents: int = 0
    availability: str = "complete"  # complete | partial | metadata_only | not_publicly_available
    document_breakdown: Dict[str, int] = Field(default_factory=dict)


class InventorySummary(BaseModel):
    """Summary metrics for documents_inventory.json."""
    total_documents_discovered: int = 0
    total_pdfs_discovered: int = 0
    total_pdfs_downloaded: int = 0
    total_pdfs_processed: int = 0
    total_html_pages: int = 0
    total_metadata_only: int = 0
    total_failed: int = 0
    total_duplicates: int = 0
    total_amendments: int = 0
    total_corrigenda: int = 0
    total_product_manuals: int = 0
    total_STIs: int = 0
    total_QCO_documents: int = 0
    total_notifications: int = 0
    total_guidelines: int = 0
    total_Hallmarking_documents: int = 0
    total_management_system_documents: int = 0
    total_laboratory_documents: int = 0
    total_certification_documents: int = 0
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
