"""
LocalVectorStore tests — real cosine-similarity math over real
DocumentChunk rows in an isolated test database, using hand-crafted vectors
(no embedding model needed for these — the vector store doesn't care how a
vector was produced).
"""

import uuid

import pytest

from app.models.document_chunk import DocumentChunk
from app.models.standard_document import StandardDocument
from app.rag.vector_store import LocalVectorStore, VectorStoreError, serialize_embedding


def _ensure_document(db_session, document_id: str) -> None:
    """Chunks are only searchable while their parent document exists — the
    vector store filters out orphans. Real ingestion always creates the
    document first, so these tests have to as well."""
    if db_session.get(StandardDocument, document_id) is not None:
        return
    db_session.add(
        StandardDocument(
            id=document_id,
            original_filename=f"{document_id}.pdf",
            file_hash=f"hash-{document_id}",
            mime_type="application/pdf",
            size_bytes=1,
            storage_path=f"/tmp/{document_id}.pdf",
        )
    )
    db_session.commit()


def _make_chunk(
    db_session, document_id: str, text: str, vector: list[float], model="test-model", chunk_index: int = 0
) -> DocumentChunk:
    _ensure_document(db_session, document_id)
    chunk = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=document_id,
        document_page_id=1,
        page_number=1,
        chunk_index=chunk_index,
        text=text,
        embedding_json=serialize_embedding(vector),
        embedding_model=model,
        embedding_dimension=len(vector),
    )
    db_session.add(chunk)
    db_session.commit()
    return chunk


def test_empty_index_returns_no_matches(db_session):
    store = LocalVectorStore()
    matches = store.similarity_search(db_session, query_vector=[1.0, 0.0, 0.0], model_name="test-model", top_k=5)
    assert matches == []


def test_identical_vector_scores_highest(db_session):
    store = LocalVectorStore()
    _make_chunk(db_session, "doc-1", "exact match", [1.0, 0.0, 0.0], chunk_index=0)
    _make_chunk(db_session, "doc-1", "orthogonal", [0.0, 1.0, 0.0], chunk_index=1)

    matches = store.similarity_search(db_session, query_vector=[1.0, 0.0, 0.0], model_name="test-model", top_k=5)
    assert len(matches) == 2
    assert matches[0].chunk.text == "exact match"
    assert matches[0].similarity_score == pytest.approx(1.0, abs=1e-5)
    assert matches[1].similarity_score == pytest.approx(0.0, abs=1e-5)


def test_results_sorted_descending_by_score(db_session):
    store = LocalVectorStore()
    _make_chunk(db_session, "doc-1", "low", [0.1, 0.9, 0.0], chunk_index=0)
    _make_chunk(db_session, "doc-1", "high", [1.0, 0.0, 0.0], chunk_index=1)
    _make_chunk(db_session, "doc-1", "medium", [0.7, 0.3, 0.0], chunk_index=2)

    matches = store.similarity_search(db_session, query_vector=[1.0, 0.0, 0.0], model_name="test-model", top_k=5)
    scores = [m.similarity_score for m in matches]
    assert scores == sorted(scores, reverse=True)


def test_top_k_limits_results(db_session):
    store = LocalVectorStore()
    for i in range(10):
        _make_chunk(db_session, "doc-1", f"chunk {i}", [1.0, float(i) / 10, 0.0], chunk_index=i)

    matches = store.similarity_search(db_session, query_vector=[1.0, 0.0, 0.0], model_name="test-model", top_k=3)
    assert len(matches) == 3


def test_document_id_filter_restricts_search_scope(db_session):
    store = LocalVectorStore()
    _make_chunk(db_session, "doc-1", "in doc 1", [1.0, 0.0, 0.0])
    _make_chunk(db_session, "doc-2", "in doc 2", [1.0, 0.0, 0.0])

    matches = store.similarity_search(
        db_session, query_vector=[1.0, 0.0, 0.0], model_name="test-model", top_k=10, document_id="doc-1"
    )
    assert len(matches) == 1
    assert matches[0].chunk.document_id == "doc-1"


def test_incompatible_model_chunks_are_excluded(db_session):
    """A chunk embedded with a different model must never be compared
    against a query from another model — this is the model/dimension
    compatibility guard."""
    store = LocalVectorStore()
    _make_chunk(db_session, "doc-1", "model A chunk", [1.0, 0.0, 0.0], model="model-a", chunk_index=0)
    _make_chunk(db_session, "doc-1", "model B chunk", [1.0, 0.0, 0.0], model="model-b", chunk_index=1)

    matches = store.similarity_search(db_session, query_vector=[1.0, 0.0, 0.0], model_name="model-a", top_k=10)
    assert len(matches) == 1
    assert matches[0].chunk.text == "model A chunk"


def test_dimension_mismatch_raises_error(db_session):
    store = LocalVectorStore()
    _make_chunk(db_session, "doc-1", "3-dim chunk", [1.0, 0.0, 0.0])

    with pytest.raises(VectorStoreError, match="dimension mismatch"):
        store.similarity_search(db_session, query_vector=[1.0, 0.0], model_name="test-model", top_k=5)


def test_zero_query_vector_raises_error(db_session):
    store = LocalVectorStore()
    _make_chunk(db_session, "doc-1", "some chunk", [1.0, 0.0, 0.0])

    with pytest.raises(VectorStoreError, match="zero vector"):
        store.similarity_search(db_session, query_vector=[0.0, 0.0, 0.0], model_name="test-model", top_k=5)


def test_unembedded_chunks_are_never_returned(db_session):
    """A chunk that exists (from chunking) but has no embedding yet must
    never appear in similarity search results."""
    store = LocalVectorStore()
    unembedded = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id="doc-1",
        document_page_id=1,
        page_number=1,
        chunk_index=0,
        text="not yet embedded",
        embedding_json=None,
        embedding_model=None,
        embedding_dimension=None,
    )
    db_session.add(unembedded)
    db_session.commit()

    matches = store.similarity_search(db_session, query_vector=[1.0, 0.0, 0.0], model_name="test-model", top_k=5)
    assert matches == []
