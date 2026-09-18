"""
DocumentPage — page-level extracted text, the core unit of source
traceability for this phase. Every downstream feature/citation points back
to a (document_id, page_number) pair, never to "the document" as an
undifferentiated blob.

`extraction_method` records how the text was obtained ("native" — pulled
directly from the PDF's text layer — or "ocr"), so a caller can tell
whether a page's text came from a Tesseract guess (with `ocr_confidence`)
or the document's own embedded text (fully reliable, no confidence score).
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        # One row per (document, page) — the natural key for this table.
        UniqueConstraint("document_id", "page_number", name="uq_document_pages_document_page"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("standard_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # "native" (PDF text layer) or "ocr" (Tesseract).
    extraction_method: Mapped[str] = mapped_column(String(10), nullable=False)
    # Only meaningful for extraction_method == "ocr"; null for native text,
    # since native extraction has no notion of confidence.
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped["StandardDocument"] = relationship("StandardDocument", back_populates="pages")
