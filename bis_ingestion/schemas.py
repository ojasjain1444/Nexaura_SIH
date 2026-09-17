"""
schemas.py — Pydantic data models for BIS Standards metadata.

Each model validates and normalises data before storage.
Provenance fields (source_url, last_checked) are mandatory on every record
so that RAG citations are always traceable to the official BIS source.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
import uuid


# ---------------------------------------------------------------------------
# Core standard record
# ---------------------------------------------------------------------------

class BISStandard(BaseModel):
    """Full metadata record for a single BIS / IS Standard."""

    # --- Identity ---
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Internal UUID for this record",
    )
    standard_number: str = Field(
        ...,
        description="Official IS number, e.g. 'IS 1', 'IS 456', 'IS 1239 Part 1'",
    )
    doc_no: Optional[str] = Field(None, description="Numeric document number extracted from IS number")
    part: Optional[str] = Field(None, description="Part number, e.g. '1', '2'")
    section: Optional[str] = Field(None, description="Section number if applicable")
    edition_year: Optional[str] = Field(None, description="Edition / publication year, e.g. '2024'")

    # --- Content ---
    title: Optional[str] = Field(None, description="Full title of the standard")
    scope: Optional[str] = Field(None, description="Scope clause or summary if available")

    # --- Status & lifecycle ---
    status: Optional[str] = Field(
        None,
        description="Status: 'In Force', 'Revised', 'Withdrawn', 'Under Revision', etc.",
    )
    publication_date: Optional[str] = Field(None, description="Publication date (YYYY-MM-DD or YYYY)")
    reaffirmation_date: Optional[str] = Field(None, description="Date of reaffirmation if any")
    withdrawal_date: Optional[str] = Field(None, description="Withdrawal date if withdrawn")

    # --- Amendments ---
    amendments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of amendment records, each with number, year, title",
    )

    # --- Relationships ---
    supersedes: Optional[str] = Field(None, description="Standard number this supersedes")
    superseded_by: Optional[str] = Field(None, description="Standard number that supersedes this")
    related_standards: list[str] = Field(
        default_factory=list,
        description="IS numbers of related standards",
    )

    # --- Classification ---
    ics_code: Optional[str] = Field(None, description="ICS (International Classification for Standards) code")
    technical_committee: Optional[str] = Field(None, description="BIS Technical Committee code, e.g. 'CED 2'")
    department: Optional[str] = Field(None, description="BIS department / division")
    product_category: Optional[str] = Field(None, description="Product category or sector")

    # --- Certification & testing ---
    certification_scheme: Optional[str] = Field(
        None,
        description="Certification scheme description (CRS, STS, STI, etc.)",
    )
    testing_information: Optional[str] = Field(
        None,
        description="Scheme of Testing and Inspection (STI) details",
    )
    has_mandatory_certification: Optional[bool] = Field(
        None,
        description="Whether this standard has mandatory BIS certification",
    )

    # --- Lab information (from LIMS) ---
    labs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of BIS-recognized labs testing for this standard",
    )

    # --- Document links ---
    source_url: str = Field(
        ...,
        description="URL of the official BIS page this record was collected from",
    )
    document_url: Optional[str] = Field(
        None,
        description="URL to the official IS document (if publicly accessible without paywall)",
    )
    amendment_urls: list[str] = Field(
        default_factory=list,
        description="URLs to publicly accessible amendment documents",
    )

    # --- Provenance ---
    source_system: str = Field(
        "BIS",
        description="Source system identifier: 'BIS', 'LIMS', 'BIS_STANDARDS_PORTAL'",
    )
    last_checked: str = Field(
        default_factory=lambda: date.today().isoformat(),
        description="Date this record was last verified against the official BIS source",
    )
    crawl_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC timestamp when this record was collected",
    )

    @field_validator("standard_number")
    @classmethod
    def normalise_standard_number(cls, v: str) -> str:
        """Normalise IS number to consistent format: 'IS XXXX' or 'IS XXXX Part N'."""
        return v.strip().upper()

    @field_validator("status")
    @classmethod
    def normalise_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        mapping = {
            "in force": "In Force",
            "current": "In Force",
            "active": "In Force",
            "revised": "Revised",
            "under revision": "Under Revision",
            "withdrawn": "Withdrawn",
            "superseded": "Superseded",
            "reaffirmed": "Reaffirmed",
        }
        return mapping.get(v.lower(), v)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "standard_number": "IS 456",
                "title": "Plain and Reinforced Concrete — Code of Practice",
                "part": None,
                "edition_year": "2000",
                "status": "In Force",
                "scope": "This standard covers the general structural use of plain and reinforced concrete.",
                "amendments": [{"number": "1", "year": "2021", "title": "Amendment No. 1"}],
                "supersedes": "IS 456 (1978)",
                "related_standards": ["IS 269", "IS 1489"],
                "certification_scheme": "Scheme II",
                "source_url": "https://standards.bis.gov.in/website/know-your-standards?standardNumber=IS456",
                "document_url": None,
                "last_checked": "2026-09-17",
            }
        }
    )


# ---------------------------------------------------------------------------
# Lab record (from LIMS)
# ---------------------------------------------------------------------------

class BISLab(BaseModel):
    """A BIS-recognized laboratory record from LIMS."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    lab_name: str
    osl_code: Optional[str] = None
    is_number: str = Field(..., description="IS number this lab is authorized to test for")
    is_doc_no: Optional[str] = None
    is_part: Optional[str] = None
    is_section: Optional[str] = None
    is_year: Optional[str] = None
    product: Optional[str] = None
    grade_type: Optional[str] = None
    testing_charges: Optional[str] = None
    validity_date: Optional[str] = None
    remark: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    source_url: str
    last_checked: str = Field(default_factory=lambda: date.today().isoformat())
    crawl_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# RAG Chunk — the unit fed into the vector store
# ---------------------------------------------------------------------------

class RAGChunk(BaseModel):
    """A chunk of text prepared for RAG ingestion with full provenance."""

    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    standard_number: str
    title: Optional[str] = None
    part: Optional[str] = None
    edition: Optional[str] = None
    clause: Optional[str] = None       # e.g. "3.1", "Scope", "Amendments"
    page: Optional[int] = None
    text: str = Field(..., description="The chunk text to be embedded")
    status: Optional[str] = None
    source_url: str = Field(..., description="Official BIS URL — mandatory for citation")
    retrieved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    token_count: Optional[int] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "chunk_id": "abc-123",
                "standard_number": "IS 456",
                "title": "Plain and Reinforced Concrete — Code of Practice",
                "part": None,
                "edition": "2000",
                "clause": "Scope",
                "page": None,
                "text": "This standard covers the general structural use...",
                "status": "In Force",
                "source_url": "https://standards.bis.gov.in/website/know-your-standards?standardNumber=IS456",
                "retrieved_at": "2026-09-17T00:00:00+00:00",
            }
        }
    )


# ---------------------------------------------------------------------------
# Crawl state — for checkpointing
# ---------------------------------------------------------------------------

class CrawlState(BaseModel):
    """Persisted state for incremental / resumable crawls."""

    last_run: Optional[str] = None
    lims_last_is_no: Optional[int] = None       # last IS doc_no processed in LIMS
    lims_last_page: Optional[int] = None        # last page processed in LIMS
    standards_portal_last_id: Optional[str] = None
    total_records_collected: int = 0
    errors_count: int = 0
    sources_completed: list[str] = Field(default_factory=list)
