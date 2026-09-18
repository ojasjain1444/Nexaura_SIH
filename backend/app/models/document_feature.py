"""
DocumentFeature — one structured, source-located fact extracted from a
document. This is the output of the feature-extraction stage (Step 5):
never a full-text blob, always a specific (feature_type, value) pair tied
to exactly where it came from.

feature_type examples (see app/ingestion/feature_extraction.py for the
actual extractors implemented in this phase): "standard_number",
"standard_title", "section_heading". Each is produced by a small,
independent extractor function — a document that yields no matches for a
given feature type simply has no row for it, rather than a null placeholder
row. This is the mechanism behind "do not assume every document contains
every feature."
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DocumentFeature(Base):
    __tablename__ = "document_features"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("standard_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Indexed: querying "all standard_number features across documents" or
    # "does this document have a section_heading feature" are both
    # plausible lookups once this table has real rows.
    feature_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    # Source traceability (Step 8) — every feature row can answer "where did
    # this come from" on its own, without joining back through DocumentPage.
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped["StandardDocument"] = relationship("StandardDocument", back_populates="features")
