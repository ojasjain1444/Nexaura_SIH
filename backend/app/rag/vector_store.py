"""
Vector store abstraction.

IMPORTANT — READ BEFORE ASSUMING THIS IS PRODUCTION VECTOR INFRASTRUCTURE:

LocalVectorStore below does similarity search with NumPy over embeddings
loaded from SQLite TEXT columns (JSON-encoded). This is a real, working,
tested implementation — but it is NOT pgvector. It has no ANN index, no
on-disk vector index, and does a linear scan of every embedded chunk on
every query. For the corpus sizes this local prototype will ever hold
(dozens to low hundreds of chunks from synthetic test documents), that is
fine. It would not scale to a real production BIS corpus with thousands of
documents.

PgVectorStore is NOT implemented in this phase. This machine has no
PostgreSQL and no Docker installed (checked directly — see
docs/RAG_RETRIEVAL.md), so a pgvector implementation could not be built and
tested honestly here. The VectorStore protocol below is written so that a
real PgVectorStore class can be added later without touching
retrieval.py or index_document.py — but until that class exists and is
actually tested against a running PostgreSQL+pgvector instance, do not
claim pgvector is implemented.
"""

import json
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.standard_document import StandardDocument


@dataclass
class SimilarityMatch:
    chunk: DocumentChunk
    similarity_score: float  # cosine similarity, range [-1, 1]; higher = more similar. NOT a confidence percentage.


class VectorStoreError(Exception):
    pass


class VectorStore(Protocol):
    def similarity_search(
        self,
        db: Session,
        query_vector: list[float],
        model_name: str,
        top_k: int,
        document_id: str | list[str] | None = None,
        document_types: list[str] | None = None,
    ) -> list[SimilarityMatch]: ...


class LocalVectorStore:
    """NumPy cosine-similarity search over DocumentChunk.embedding_json.
    See module docstring — this is the local-development implementation,
    explicitly not equivalent to pgvector."""

    def similarity_search(
        self,
        db: Session,
        query_vector: list[float],
        model_name: str,
        top_k: int,
        document_id: str | list[str] | None = None,
        document_types: list[str] | None = None,
    ) -> list[SimilarityMatch]:
        stmt = select(DocumentChunk).where(
            DocumentChunk.embedding_json.is_not(None),
            # Compatibility guard: never compare vectors from different
            # embedding models — see app/models/document_chunk.py.
            DocumentChunk.embedding_model == model_name,
            # SQLite runs with PRAGMA foreign_keys off, so a delete that
            # bypasses the ORM cascade leaves chunks whose parent document is
            # gone. Those still carry valid embeddings and would otherwise
            # rank as live hits citing "(unknown document)".
            DocumentChunk.document_id.in_(select(StandardDocument.id)),
        )
        if document_id is not None:
            # Accepts a single ID (Phase 4 usage: filter to one document) or
            # a list (Phase 5 addition: filter to every document linked to
            # one Standard — see RetrievalService.retrieve's standard_id
            # handling).
            if isinstance(document_id, list):
                if not document_id:
                    return []  # an empty ID list can never match anything
                stmt = stmt.where(DocumentChunk.document_id.in_(document_id))
            else:
                stmt = stmt.where(DocumentChunk.document_id == document_id)

        if document_types is not None:
            # Phase 12: DocumentChunk has no document_type of its own — it
            # belongs to the owning StandardDocument — so this is a join,
            # not a direct column filter. An empty list can never match
            # anything, same convention as an empty document_id list above.
            if not document_types:
                return []
            stmt = stmt.join(StandardDocument, DocumentChunk.document_id == StandardDocument.id).where(
                StandardDocument.document_type.in_(document_types)
            )

        chunks = list(db.execute(stmt).scalars().all())
        if not chunks:
            return []

        query_np = np.array(query_vector, dtype=np.float32)
        query_norm = np.linalg.norm(query_np)
        if query_norm == 0:
            raise VectorStoreError("Query embedding is a zero vector; cannot compute similarity.")

        matches: list[SimilarityMatch] = []
        for chunk in chunks:
            try:
                chunk_vector = json.loads(chunk.embedding_json)
            except (json.JSONDecodeError, TypeError) as exc:
                raise VectorStoreError(f"Corrupt embedding for chunk {chunk.id}: {exc}") from exc

            chunk_np = np.array(chunk_vector, dtype=np.float32)
            if chunk_np.shape[0] != query_np.shape[0]:
                raise VectorStoreError(
                    f"Embedding dimension mismatch: query has {query_np.shape[0]}, "
                    f"chunk {chunk.id} has {chunk_np.shape[0]}"
                )

            chunk_norm = np.linalg.norm(chunk_np)
            if chunk_norm == 0:
                continue  # a genuinely zero-vector chunk can never match anything; skip rather than divide by zero
            cosine_similarity = float(np.dot(query_np, chunk_np) / (query_norm * chunk_norm))
            matches.append(SimilarityMatch(chunk=chunk, similarity_score=cosine_similarity))

        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        return matches[:top_k]


def serialize_embedding(vector: list[float]) -> str:
    return json.dumps(vector)


def get_vector_store() -> VectorStore:
    # Only one implementation exists in this phase. If EMBEDDING_PROVIDER-
    # style configuration for the vector store backend is added later
    # (e.g. VECTOR_STORE=pgvector), this function is where that branch goes.
    return LocalVectorStore()
