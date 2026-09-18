"""
StandardScope — a standard's own stated applicability, extracted once at
ingestion time from its "1 SCOPE" clause.

Real BIS standards consistently open with a numbered SCOPE clause that is
the standard's own authoritative statement of what product/use-case it
covers (confirmed across multiple genuine BIS PDFs, e.g. IS 10500's
"This standard prescribes the requirements and the methods of sampling and
test for drinking water."). Storing this text as a first-class, queryable
fact — rather than relying on whichever chunk retrieval happens to surface
containing a keyword match — lets applicability checking compare a user's
product against the standard's actual self-declared scope.

At most one row per document: a document with no detectable SCOPE clause
(e.g. features_extraction.py's SECTION_HEADING_PATTERN never matches "1
SCOPE" in its text) simply has no row, rather than a null-filled
placeholder — same "no guessing" convention as DocumentFeature and the
extracted_* fields on StandardDocument.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StandardScope(Base):
    __tablename__ = "standard_scopes"
    __table_args__ = (UniqueConstraint("document_id", name="uq_standard_scopes_document_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("standard_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Verbatim clause text — never LLM-rewritten, so this can never
    # fabricate what a standard claims to cover.
    scope_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped["StandardDocument"] = relationship("StandardDocument", back_populates="scope")
