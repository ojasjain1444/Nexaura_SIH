"""
Schemas for POST /api/rag/retrieve.

This is retrieval only — evidence chunks with similarity scores. No answer
text is generated here; there is no LLM call anywhere in this module or
its callers.
"""

from pydantic import BaseModel, Field, field_validator

MAX_TOP_K = 20
MAX_QUERY_LENGTH = 1000


class RetrievalRequest(BaseModel):
    query: str
    top_k: int = 5
    document_id: str | None = None

    @field_validator("query")
    @classmethod
    def query_must_be_reasonable(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be empty")
        if len(stripped) > MAX_QUERY_LENGTH:
            raise ValueError(f"query must not exceed {MAX_QUERY_LENGTH} characters")
        return stripped

    @field_validator("top_k")
    @classmethod
    def top_k_must_be_in_range(cls, value: int) -> int:
        if value < 1 or value > MAX_TOP_K:
            raise ValueError(f"top_k must be between 1 and {MAX_TOP_K}")
        return value


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    # Phase 12: the owning document's classification (see
    # app.product.document_type.DocumentType), carried alongside the
    # existing citation fields for evidence traceability. Optional/nullable
    # since retrieval predates this field — a chunk from before Phase 12,
    # or any caller not resolving it, still constructs a valid RetrievedChunk.
    document_type: str | None = None
    page_number: int
    section: str | None
    text: str
    similarity_score: float = Field(description="Cosine similarity in [-1, 1]. Higher = more similar. Not a confidence percentage.")


class RetrievalResponse(BaseModel):
    results: list[RetrievedChunk]
