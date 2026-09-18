"""
CandidateStandard — Phase 10, extended in Phase 13.

A retrieved piece of evidence is not automatically an applicable
requirement. This schema represents a candidate produced by hybrid
retrieval (app/product/hybrid_retrieval.py) before the applicability
engine (app/product/applicability.py) has made any determination about it.

Deliberately Pydantic-only, not a database model: a CandidateStandard is a
transient, per-request analysis result — it is never persisted as its own
row. What IS persisted (unchanged from Phase 5) is MessageCitation, built
from the same underlying RetrievedChunk evidence once a chat response is
actually generated.

No numeric "compliance score" is exposed — relevance_score is the honest
retrieval signal (cosine similarity or BM25, whichever contributed), never
reinterpreted as a probability of applicability or compliance.

Phase 13 adds optional score-breakdown fields (semantic_score,
keyword_score, document_type_boost, final_score) — see
app/product/scoring.py for exactly how they're computed. These are
developer/debugging explanation data, never surfaced to end users in chat
prose (discovery_response.py's system prompt already forbids the LLM from
inventing its own relevance explanations — these fields exist so a human
reviewing logs/tests can answer "why did this rank here," not so the
assistant narrates them). All optional/default-None so any caller
constructing a CandidateStandard without them (e.g. existing tests) still
produces a valid object.
"""

from enum import Enum

from pydantic import BaseModel

from app.schemas.retrieval import RetrievedChunk


class ApplicabilityStatus(str, Enum):
    APPLICABLE = "APPLICABLE"
    POTENTIALLY_APPLICABLE = "POTENTIALLY_APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class CandidateStandard(BaseModel):
    document_id: str
    standard_id: str | None
    document_name: str
    relevance_score: float
    matched_terms: list[str]
    evidence: list[RetrievedChunk]
    applicability_status: ApplicabilityStatus
    # Short, human-readable reason for the applicability_status — always
    # derived from the actual evidence/profile state, never invented
    # justification. See applicability.py for exactly how this is built.
    applicability_reason: str
    # Phase 13 — see app/product/scoring.py. None for any candidate built
    # without the new reranking path (kept optional for exactly that
    # backward-compatibility reason).
    semantic_score: float | None = None
    keyword_score: float | None = None
    document_type_boost: float | None = None
    exact_identifier_boost: float | None = None
    profile_attribute_boost: float | None = None
    final_score: float | None = None
