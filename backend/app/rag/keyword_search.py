"""
KeywordSearchService — Phase 10: local lexical (BM25) search over
DocumentChunk text, using SQLite's built-in FTS5 virtual table.

This is additive, not a replacement: app/rag/retrieval.py's semantic
RetrievalService and LocalVectorStore are completely untouched. This
module exists solely so app/product/hybrid_retrieval.py can combine
semantic similarity with lexical keyword matching — useful when a product
attribute (e.g. an exact technology name or an IS number) is a strong
literal signal that embedding similarity alone might under-rank.

Why a standalone FTS5 table rather than SQLite's "external content" mode
(content=document_chunks): external-content FTS5 requires the content
table's rowid to be a plain INTEGER PRIMARY KEY, but DocumentChunk.id is a
UUID string (see app/models/document_chunk.py) — not row-aliasable. A
standalone table avoids that constraint entirely, at the cost of needing
explicit sync calls (index_chunks / delete_document_chunks below) rather
than automatic triggers. Both are called from the same places
app/rag/index_document.py already creates/deletes DocumentChunk rows, so
the FTS table never drifts out of sync with the real chunk table.

No SQLAlchemy model wraps this table — FTS5 virtual tables are not
representable as a normal ORM-mapped class, so this module talks to it via
raw SQL through the session's underlying DBAPI connection.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

FTS_TABLE = "document_chunks_fts"


@dataclass
class KeywordMatch:
    chunk_id: str
    document_id: str
    text: str
    bm25_score: float  # SQLite's raw bm25(): more negative = more relevant


class KeywordSearchError(Exception):
    pass


def index_chunks(db: Session, document_id: str, chunks: list[tuple[str, str]]) -> None:
    """Populates the FTS table for one document's chunks.
    `chunks` is a list of (chunk_id, text) tuples. Always deletes any
    existing rows for this document first (see delete_document_chunks) so
    this is safe to call repeatedly on re-index, matching
    ChunkRepository.delete_by_document's own re-run safety."""
    delete_document_chunks(db, document_id)
    if not chunks:
        return
    db.execute(
        text(f"INSERT INTO {FTS_TABLE} (chunk_id, document_id, text) VALUES (:chunk_id, :document_id, :text)"),
        [{"chunk_id": chunk_id, "document_id": document_id, "text": chunk_text} for chunk_id, chunk_text in chunks],
    )
    db.commit()


def delete_document_chunks(db: Session, document_id: str) -> None:
    db.execute(text(f"DELETE FROM {FTS_TABLE} WHERE document_id = :document_id"), {"document_id": document_id})
    db.commit()


def search(db: Session, query: str, top_k: int, document_ids: list[str] | None = None) -> list[KeywordMatch]:
    """BM25-ranked lexical search. An empty/whitespace-only query, or a
    query with no matches, returns [] — never an error; a keyword search
    finding nothing is a normal, honest outcome, not a failure."""
    if not query or not query.strip():
        return []
    if document_ids is not None and not document_ids:
        return []  # an empty ID list can never match anything

    params: dict = {"query": query, "top_k": top_k}
    document_filter = ""
    if document_ids is not None:
        placeholders = ", ".join(f":doc_{i}" for i in range(len(document_ids)))
        document_filter = f"AND document_id IN ({placeholders})"
        for i, doc_id in enumerate(document_ids):
            params[f"doc_{i}"] = doc_id

    try:
        rows = db.execute(
            text(
                f"""
                SELECT chunk_id, document_id, text, bm25({FTS_TABLE}) AS score
                FROM {FTS_TABLE}
                WHERE {FTS_TABLE} MATCH :query {document_filter}
                ORDER BY score
                LIMIT :top_k
                """
            ),
            params,
        ).fetchall()
    except Exception as exc:
        # A malformed FTS5 query (e.g. unbalanced quotes in user-typed
        # search syntax) must degrade to "no keyword matches", not crash
        # the whole hybrid retrieval call — semantic search still runs.
        raise KeywordSearchError(f"Keyword search failed for query {query!r}: {exc}") from exc

    return [KeywordMatch(chunk_id=r.chunk_id, document_id=r.document_id, text=r.text, bm25_score=r.score) for r in rows]
