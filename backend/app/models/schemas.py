"""
backend/app/models/schemas.py — Pydantic models for the Nexaura API.
"""

from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


# --- Standards Schemas --------------------------------------------------------

class StandardSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    standard_number: str
    title: str
    edition_year: Optional[str] = None
    status: Optional[str] = "IN FORCE"
    technical_committee: Optional[str] = None
    department: Optional[str] = None
    has_pdf: bool = False
    source_url: str


class StandardDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    standard_number: str
    doc_no: Optional[str] = None
    title: str
    edition_year: Optional[str] = None
    status: Optional[str] = "IN FORCE"
    scope: Optional[str] = None
    publication_date: Optional[str] = None
    valid_upto: Optional[str] = None
    technical_committee: Optional[str] = None
    department: Optional[str] = None
    amendments: list[Any] = Field(default_factory=list)
    has_mandatory_certification: Optional[bool] = None
    has_pdf: bool = False
    pdf_filename: Optional[str] = None
    pdf_pages_indexed: Optional[int] = 0
    gridfs_id: Optional[str] = None
    source_url: str
    source_system: str = "OFFICIAL_BIS"


# --- Labs Schemas -------------------------------------------------------------

class LabResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lab_name: str
    osl_code: Optional[str] = None
    is_number: str
    is_doc_no: Optional[str] = None
    product: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    remark: Optional[str] = None
    source_url: Optional[str] = None


# --- RAG Schemas --------------------------------------------------------------

class RAGChunkResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chunk_id: str
    standard_number: str
    text: str
    token_count: int
    source_url: str
    section: Optional[str] = None
    score: Optional[float] = None


class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, description="Question or search query about Indian Standards")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of context chunks to retrieve")
    standard_number: Optional[str] = Field(default=None, description="Optional filter for a specific standard (e.g. 'IS 456')")


class RAGQueryResponse(BaseModel):
    query: str
    answer: str
    cited_standards: list[str]
    citations: list[dict[str, str]]
    chunks: list[RAGChunkResponse]


# --- Pagination ---------------------------------------------------------------

class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: list[T]


# --- Stats & System -----------------------------------------------------------

class StatsResponse(BaseModel):
    standards_count: int
    labs_count: int
    rag_chunks_count: int
    pdf_documents_count: int
    gridfs_files_count: int
    database_name: str
    status: str = "healthy"


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    database_connected: bool
    total_standards: int
