"""
Document indexing — chunking + embedding, as an explicit operation separate
from the Phase 3 ingestion pipeline (app/ingestion/pipeline.py).

Why separate: per Phase 4's Step 12, a failed embedding step must never
threaten the already-completed text_extracted/features_extracted state
from Phase 3. Indexing only runs against a document whose Phase 3
processing already reached "completed" — it reads DocumentPage rows that
already exist and never re-runs extraction/OCR.

Safe to re-run: indexing a document that already has chunks deletes and
recreates them (see ChunkRepository.delete_by_document) rather than
appending — running `index_document` twice never produces duplicate or
stale chunks.
"""

import logging
import uuid

from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.rag.chunking import chunk_page_text
from app.rag.embeddings import EmbeddingError, EmbeddingProvider, get_embedding_provider
from app.rag.keyword_search import index_chunks as index_chunks_for_keyword_search
from app.rag.vector_store import serialize_embedding
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository

logger = logging.getLogger("bis_sahayak")

# E5 models expect a "passage: " instruction prefix on indexed text (see
# app/rag/embeddings.py) — applied here, not stored as part of the chunk's
# displayed text.
PASSAGE_PREFIX = "passage: "


class IndexingError(Exception):
    pass


class IndexingResult:
    def __init__(self, document_id: str, chunks_created: int, chunks_embedded: int):
        self.document_id = document_id
        self.chunks_created = chunks_created
        self.chunks_embedded = chunks_embedded


def index_document(db: Session, document_id: str, embedding_provider: EmbeddingProvider | None = None) -> IndexingResult:
    embedding_provider = embedding_provider or get_embedding_provider()
    doc_repo = DocumentRepository(db)
    chunk_repo = ChunkRepository(db)

    document = doc_repo.get_with_pages(document_id)
    if document is None:
        raise IndexingError(f"Document {document_id} not found")

    if document.status not in ("completed",):
        raise IndexingError(
            f"Document {document_id} has status '{document.status}', not 'completed'. "
            "Only fully-processed documents can be indexed."
        )

    # Re-indexing safety: wipe any prior chunks for this document before
    # recreating them, so re-running never accumulates duplicates.
    chunk_repo.delete_by_document(document_id)

    chunk_records: list[DocumentChunk] = []
    for page in document.pages:
        page_chunks = chunk_page_text(page.text)
        for chunk in page_chunks:
            chunk_records.append(
                DocumentChunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    document_page_id=page.id,
                    page_number=page.page_number,
                    chunk_index=len(chunk_records),
                    text=chunk.text,
                    section=chunk.section,
                )
            )

    if not chunk_records:
        logger.warning("Document %s produced zero chunks (no extractable text on any page)", document_id)
        return IndexingResult(document_id=document_id, chunks_created=0, chunks_embedded=0)

    try:
        texts_to_embed = [PASSAGE_PREFIX + record.text for record in chunk_records]
        vectors = embedding_provider.embed_texts(texts_to_embed)
    except EmbeddingError as exc:
        raise IndexingError(f"Embedding failed: {exc}") from exc

    if len(vectors) != len(chunk_records):
        raise IndexingError(
            f"Embedding provider returned {len(vectors)} vectors for {len(chunk_records)} chunks — mismatch."
        )

    for record, vector in zip(chunk_records, vectors):
        record.embedding_json = serialize_embedding(vector)
        record.embedding_model = embedding_provider.model_name
        record.embedding_dimension = embedding_provider.dimension

    for record in chunk_records:
        chunk_repo.add_chunk(record)

    # Phase 10: keep the FTS5 keyword index in sync with the same chunks
    # just (re)created above — additive to the existing embedding index,
    # never a replacement for it. A failure here must not undo the
    # embedding work that already succeeded and committed.
    index_chunks_for_keyword_search(db, document_id, [(record.id, record.text) for record in chunk_records])

    return IndexingResult(
        document_id=document_id, chunks_created=len(chunk_records), chunks_embedded=len(chunk_records)
    )
