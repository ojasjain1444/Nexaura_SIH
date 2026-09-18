"""
StandardRequirement — one obligation-bearing clause detected in a
standard, extracted once at ingestion time.

This precomputes exactly the same detection app/product/requirement_extraction.py
already did at query time (an explicit obligation word — "shall"/"must"/
"required"/"requirement" — co-occurring with one of CATEGORY_KEYWORDS'
category words), but runs it once per document over the document's own
pages rather than re-running it per-query over whatever chunks retrieval
happened to return. requirement_extraction.py now reads these rows
(scoped to a candidate's retrieved evidence pages) instead of re-scanning
chunk text — see that module for how detection results are turned into a
user-facing ComplianceRequirement. category/clause_number use the exact
same category and section-heading detection as the rest of the ingestion
pipeline (CATEGORY_KEYWORDS, SECTION_HEADING_PATTERN) so this table can
never disagree with what a live query would have found from the same text.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StandardRequirement(Base):
    __tablename__ = "standard_requirements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("standard_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # RequirementCategory enum value (see app/schemas/compliance.py) stored
    # as plain text — indexed since "all TESTING requirements across
    # standards" is a plausible future lookup, matching DocumentFeature's
    # own feature_type indexing convention.
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    clause_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Other IS-standard numbers this clause references (e.g. "tested in
    # accordance with IS 1622") — comma-joined plain text, not a separate
    # table: this is a denormalized, read-mostly convenience field, not a
    # relationship anything joins against.
    referenced_standards: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped["StandardDocument"] = relationship("StandardDocument", back_populates="requirements")
