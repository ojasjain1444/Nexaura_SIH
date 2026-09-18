"""
RegulatoryEvidence — Phase 12.

Represents regulatory/QCO evidence for a StandardDocument, kept
deliberately SEPARATE from ApplicabilityStatus (app/schemas/candidate_standard.py)
and RegulatoryStatus (app/schemas/compliance.py): a document being a
relevant/applicable Indian Standard does not, by itself, establish that
BIS certification is mandatory for a product. This table is where an
actual mandatory-status determination would eventually be recorded, once
real regulatory source material exists to record it from.

CRITICAL GOVERNANCE: no ingestion code, no LLM, and no rule anywhere in
this codebase creates or populates a RegulatoryEvidence row. A row here
represents a human-recorded fact ("this document's regulatory context has
been reviewed and here is what was found"), exactly analogous to how
StandardDocument.source_type="verified_bis" must never be set by the
pipeline itself. mandatory_status defaults to "NOT_DETERMINED" and stays
there unless a row is explicitly created with real evidence — there is no
code path in this project, as of Phase 12, that ever sets it to
"MANDATORY". This is intentional: no QCO/regulatory-order corpus exists
yet (see docs on REAL BIS DATA STATUS), so a real MANDATORY determination
cannot be made honestly today.

Modeled as a structured table (not JSON) per this project's established
convention (see app/models/certification_scheme.py, app/models/product_profile.py).
related_standard_ids is a join table, not an array/JSON column, for the
same reason app/models/standard.py uses StandardRelatedCode instead of an
array column.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Deliberately conservative: NOT_DETERMINED is the only value any code in
# this project ever assigns automatically. MANDATORY/NOT_MANDATORY may only
# ever be set by an explicit human action recording real regulatory
# evidence — never guessed, never inferred from semantic similarity.
MANDATORY_STATUS_VALUES = ("MANDATORY", "NOT_MANDATORY", "NOT_DETERMINED")
DEFAULT_MANDATORY_STATUS = "NOT_DETERMINED"


class RegulatoryEvidence(Base):
    __tablename__ = "regulatory_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("standard_documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    # A citation/reference to the actual regulatory instrument (e.g. a QCO
    # gazette notification number) — free text because this project has no
    # controlled vocabulary for regulatory instrument identifiers, and
    # inventing one without real examples to model it on would be
    # speculative.
    regulatory_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    product_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mandatory_status: Mapped[str] = mapped_column(String(20), nullable=False, default=DEFAULT_MANDATORY_STATUS)
    scheme: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    document: Mapped["StandardDocument"] = relationship("StandardDocument", back_populates="regulatory_evidence")
    related_standards: Mapped[list["RegulatoryEvidenceRelatedStandard"]] = relationship(
        "RegulatoryEvidenceRelatedStandard", back_populates="regulatory_evidence", cascade="all, delete-orphan"
    )


class RegulatoryEvidenceRelatedStandard(Base):
    """Join table: which Standard row(s) a piece of regulatory evidence
    relates to. A plain child table, not an array/JSON column — consistent
    with app/models/standard.py's StandardRelatedCode."""

    __tablename__ = "regulatory_evidence_related_standards"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    regulatory_evidence_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("regulatory_evidence.id", ondelete="CASCADE"), nullable=False, index=True
    )
    standard_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("standards.id", ondelete="CASCADE"), nullable=False, index=True
    )

    regulatory_evidence: Mapped["RegulatoryEvidence"] = relationship(
        "RegulatoryEvidence", back_populates="related_standards"
    )
