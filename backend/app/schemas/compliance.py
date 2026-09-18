"""
Compliance requirement / checklist schemas — Phase 11.

Deliberately Pydantic-only, not database models — matching CandidateStandard
(app/schemas/candidate_standard.py): a ComplianceRequirement/ComplianceChecklist
is a transient, per-turn analysis result assembled fresh from the current
ProductProfile + CandidateStandard evidence, never persisted as its own
row. What IS persisted (unchanged from Phase 5) is MessageCitation, built
from the same underlying RetrievedChunk evidence once a chat response is
generated — this module introduces no second citation system.

RequirementCategory and RequirementStatus are both controlled enums.
app/product/requirement_extraction.py is the only place that constructs a
ComplianceRequirement, and it only ever assigns one of these fixed values —
never an arbitrary category string an LLM might propose (see that module's
docstring for why category assignment is pure keyword/pattern matching,
not an LLM judgment call).

RegulatoryStatus is a SEPARATE field from RequirementStatus, per the Phase
11 brief's explicit requirement to never conflate "this requirement is
confirmed relevant" with "this requirement is legally mandatory." No rule
in this codebase can currently produce MANDATORY_CONFIRMED — there is no
QCO/regulatory-order metadata anywhere in this project's schema (see
app/models/standard.py, app/models/standard_document.py) — so every
requirement's regulatory_status is NOT_DETERMINED until a future phase
adds real regulatory evidence to check against. This is intentional
honesty, not an oversight.

No numeric "compliance score" or "launch readiness percentage" field
exists here or anywhere else in this schema, per explicit instruction.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.candidate_standard import CandidateStandard
from app.schemas.product_profile import ProductProfileResponse
from app.schemas.retrieval import RetrievedChunk


class RequirementCategory(str, Enum):
    TESTING = "TESTING"
    DOCUMENTATION = "DOCUMENTATION"
    CERTIFICATION = "CERTIFICATION"
    CONFORMITY_ASSESSMENT = "CONFORMITY_ASSESSMENT"
    MARKING = "MARKING"
    MANUFACTURING_QUALITY = "MANUFACTURING_QUALITY"
    OTHER = "OTHER"


class RequirementStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    POTENTIALLY_APPLICABLE = "POTENTIALLY_APPLICABLE"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RegulatoryStatus(str, Enum):
    MANDATORY_CONFIRMED = "MANDATORY_CONFIRMED"
    VOLUNTARY_OR_NON_MANDATORY = "VOLUNTARY_OR_NON_MANDATORY"
    NOT_DETERMINED = "NOT_DETERMINED"


class ComplianceRequirement(BaseModel):
    id: str
    title: str
    description: str
    category: RequirementCategory
    status: RequirementStatus
    regulatory_status: RegulatoryStatus
    evidence: list[RetrievedChunk]
    source_document_ids: list[str]
    applicable_standard_id: str | None
    notes: str | None = None


class ComplianceChecklist(BaseModel):
    product_profile: ProductProfileResponse
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    candidate_standards: list[CandidateStandard]
    items: list[ComplianceRequirement]
    open_questions: list[str]
