from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk


class ChunkRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_document(self, document_id: str) -> list[DocumentChunk]:
        stmt = select(DocumentChunk).where(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index)
        return list(self.db.execute(stmt).scalars().all())

    def delete_by_document(self, document_id: str) -> int:
        """Deletes all chunks for a document — the mechanism that makes
        re-indexing safe (chunks are recreated fresh, never appended to
        stale ones)."""
        stmt = delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount

    def add_chunk(self, chunk: DocumentChunk) -> DocumentChunk:
        self.db.add(chunk)
        self.db.commit()
        self.db.refresh(chunk)
        return chunk

    def count_embedded(self, document_id: str) -> int:
        stmt = select(DocumentChunk).where(
            DocumentChunk.document_id == document_id, DocumentChunk.embedding_json.is_not(None)
        )
        return len(list(self.db.execute(stmt).scalars().all()))
