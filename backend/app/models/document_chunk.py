"""
DocumentChunk — a retrieval-sized slice of a document's text, with the
embedding stored directly on the row.

Design decision (embedding on DocumentChunk vs. a separate Embedding
table): a chunk has exactly one active embedding at a time in this phase —
there is no requirement yet to store multiple simultaneous embeddings per
chunk (e.g. to compare two providers side by side). Storing the vector
directly here avoids a join on every retrieval query and keeps
`embedding_model`/`embedding_dimension` co-located with the vector they
describe, which is what makes the compatibility check in
app/rag/vector_store.py a single-row read rather than a join. If a future
phase needs multiple embeddings per chunk, that is the point at which to
introduce a separate Embedding table — not before.

The embedding vector itself is stored as JSON-encoded text
(`embedding_json`), not a native vector column: SQLite has no vector type,
and this project's local-dev database is SQLite (see docs/DATABASE.md).
The `app/rag/vector_store.py` LocalVectorStore reads this column and does
similarity search in NumPy; a future PostgreSQL+pgvector VectorStore
implementation would instead use a real `vector` column — see
docs/RAG_RETRIEVAL.md for why pgvector was not adopted in this phase (no
PostgreSQL/Docker available on the reference dev machine).

`embedding_model` and `embedding_dimension` together are how the system
detects an incompatible embedding: a query embedded with a different model
must never be compared against a chunk embedded with another — see
app/rag/vector_store.py's compatibility check.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        # A document's chunks are produced deterministically and indexed by
        # position — re-indexing must be able to identify "chunk 3 of
        # document X" unambiguously to support safe re-runs.
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_chunk_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("standard_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # DocumentPage.id is an integer PK (see app/models/document_page.py) —
    # matched here, not a UUID string.
    document_page_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Embedding — nullable because a chunk can exist (from chunking) before
    # it has been embedded (indexing is a separate, explicit step — see
    # app/rag/index_document.py). A chunk with embedding_vector is None has
    # simply not been indexed yet, which is the honest state, not a bug.
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Indexed: the vector store must filter to only chunks embedded with a
    # given model/dimension before doing any similarity math — this is the
    # mechanism that prevents mixing incompatible embeddings.
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped["StandardDocument"] = relationship("StandardDocument", back_populates="chunks")
