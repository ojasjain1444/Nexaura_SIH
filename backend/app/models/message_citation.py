"""
MessageCitation — persisted source-attribution rows for an assistant
Message, so citations survive a page reload / conversation reopen from
history, not just the immediate chat response.

Citation values are copied from the actual RetrievalService result at the
moment the message was generated (document_id, document_name, page_number,
section, chunk_id) — never invented by the LLM. See
app/services/chat_service.py for where these rows are created.

document_id/chunk_id are NOT foreign keys to StandardDocument/DocumentChunk:
a chunk or document could theoretically be deleted/re-indexed after a
citation was recorded, and the citation should remain a truthful record of
what evidence was used *at the time*, not silently disappear or dangle. If
future auditing needs a live join back to the source, that is a
deliberately separate concern from "what did the assistant cite."
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MessageCitation(Base):
    __tablename__ = "message_citations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    document_name: Mapped[str] = mapped_column(String(500), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_id: Mapped[str] = mapped_column(String(36), nullable=False)
    similarity_score: Mapped[float] = mapped_column(nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    message: Mapped["Message"] = relationship("Message", back_populates="citations")
