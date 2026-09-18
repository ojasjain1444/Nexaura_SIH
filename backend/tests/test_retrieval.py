"""
RetrievalService and POST /api/rag/retrieve tests.

Uses a deterministic FakeEmbeddingProvider so tests are fast and don't
depend on the real model's semantic judgment for pass/fail — the real
model's actual retrieval quality is exercised separately in
test_retrieval_evaluation.py (marked slow).
"""

import uuid

import pytest

from app.models.document_chunk import DocumentChunk
from app.models.standard_document import StandardDocument
from app.rag.retrieval import RetrievalError, RetrievalService, looks_off_corpus
from app.rag.vector_store import serialize_embedding
from app.schemas.retrieval import RetrievedChunk
from tests.test_embeddings import FakeEmbeddingProvider


def _make_document(db_session, doc_id: str, filename: str = "test.pdf") -> StandardDocument:
    document = StandardDocument(
        id=doc_id,
        original_filename=filename,
        file_hash=f"hash-{doc_id}",
        mime_type="application/pdf",
        size_bytes=100,
        storage_path="/tmp/fake.pdf",
        status="completed",
        source_type="test",
    )
    db_session.add(document)
    db_session.commit()
    return document


def _make_chunk(db_session, document_id: str, text: str, vector: list[float], chunk_index: int, page: int = 1, section=None):
    chunk = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=document_id,
        document_page_id=1,
        page_number=page,
        chunk_index=chunk_index,
        text=text,
        section=section,
        embedding_json=serialize_embedding(vector),
        embedding_model="fake-test-model",
        embedding_dimension=len(vector),
    )
    db_session.add(chunk)
    db_session.commit()
    return chunk


# --- Service-level tests ---


def test_retrieval_on_empty_index_returns_no_results(db_session):
    service = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    results = service.retrieve(query="anything", top_k=5)
    assert results == []


def test_retrieval_returns_source_provenance(db_session):
    doc = _make_document(db_session, "doc-1", "standard.pdf")
    provider = FakeEmbeddingProvider()
    vector = provider.embed_text("passage: some text")
    _make_chunk(db_session, doc.id, "some relevant text", vector, chunk_index=0, page=3, section="4.2")

    service = RetrievalService(db_session, embedding_provider=provider)
    results = service.retrieve(query="some text", top_k=5)

    assert len(results) == 1
    assert results[0].document_id == doc.id
    assert results[0].document_name == "standard.pdf"
    assert results[0].page_number == 3
    assert results[0].section == "4.2"
    assert results[0].text == "some relevant text"


def test_retrieval_with_invalid_document_id_raises(db_session):
    service = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    with pytest.raises(RetrievalError, match="does not exist"):
        service.retrieve(query="test", top_k=5, document_id="does-not-exist")


def test_retrieval_filters_by_document_id(db_session):
    doc1 = _make_document(db_session, "doc-1")
    doc2 = _make_document(db_session, "doc-2")
    provider = FakeEmbeddingProvider()
    v1 = provider.embed_text("passage: doc one content")
    v2 = provider.embed_text("passage: doc two content")
    _make_chunk(db_session, doc1.id, "doc one content", v1, chunk_index=0)
    _make_chunk(db_session, doc2.id, "doc two content", v2, chunk_index=0)

    service = RetrievalService(db_session, embedding_provider=provider)
    results = service.retrieve(query="content", top_k=10, document_id=doc1.id)

    assert len(results) == 1
    assert results[0].document_id == doc1.id


# --- API-level tests ---


def test_retrieve_endpoint_rejects_empty_query(client):
    response = client.post("/api/rag/retrieve", json={"query": "   "})
    assert response.status_code == 422


def test_retrieve_endpoint_rejects_oversized_top_k(client):
    response = client.post("/api/rag/retrieve", json={"query": "test", "top_k": 1000})
    assert response.status_code == 422


def test_retrieve_endpoint_rejects_zero_top_k(client):
    response = client.post("/api/rag/retrieve", json={"query": "test", "top_k": 0})
    assert response.status_code == 422


def test_retrieve_endpoint_rejects_oversized_query(client):
    response = client.post("/api/rag/retrieve", json={"query": "x" * 2000})
    assert response.status_code == 422


def test_retrieve_endpoint_invalid_document_id_returns_422(client):
    response = client.post("/api/rag/retrieve", json={"query": "test", "document_id": "does-not-exist"})
    assert response.status_code == 422


def test_retrieve_endpoint_empty_index_returns_empty_results(client):
    response = client.post("/api/rag/retrieve", json={"query": "anything at all"})
    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_retrieve_endpoint_response_shape(client, db_session):
    doc = _make_document(db_session, "doc-shape-test")
    # Use the real default provider path through the API, but seed a chunk
    # with a vector compatible with whatever the API's default embedding
    # provider actually is — simplest is to hit the API's own embed to get
    # a same-space vector via the retrieval service the endpoint uses.
    from app.core.config import get_settings
    from app.rag.embeddings import get_embedding_provider

    provider = get_embedding_provider()
    vector = provider.embed_texts(["passage: shape test content"])[0]
    _make_chunk(db_session, doc.id, "shape test content", vector, chunk_index=0)

    response = client.post("/api/rag/retrieve", json={"query": "shape test"})
    assert response.status_code == 200
    body = response.json()
    assert "results" in body
    if body["results"]:
        result = body["results"][0]
        assert set(result.keys()) == {
            "chunk_id",
            "document_id",
            "document_name",
            "page_number",
            "section",
            "text",
            "similarity_score",
        }


def _chunk(text: str, score: float = 0.85) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="c",
        document_id="d",
        document_name="IS_456_2000.pdf",
        document_type=None,
        page_number=1,
        section=None,
        text=text,
        similarity_score=score,
    )


CONCRETE_EVIDENCE = [
    _chunk("The minimum grade of concrete for reinforced concrete work shall be M20."),
    _chunk("Durability requirements depend on exposure condition and cement content."),
]


def test_off_corpus_detected_when_subject_absent_from_evidence():
    """Retrieval always returns its nearest neighbours, so an unanswerable
    question still comes back with confident-looking concrete clauses. The
    giveaway is that what the question is actually about appears nowhere in
    them."""
    assert looks_off_corpus("which IS standard applies to laptops", CONCRETE_EVIDENCE) is True
    assert looks_off_corpus("for a wooden chair", CONCRETE_EVIDENCE) is True
    assert looks_off_corpus("certification process for shampoo", CONCRETE_EVIDENCE) is True


def test_answerable_question_is_not_flagged():
    assert looks_off_corpus("what is the minimum grade of concrete?", CONCRETE_EVIDENCE) is False
    assert looks_off_corpus("durability and exposure requirements", CONCRETE_EVIDENCE) is False


def test_register_words_alone_do_not_ground_a_question():
    """"standard", "certification" and friends appear in every standards
    document, so grounding on them would mark any off-topic question as
    covered."""
    evidence = [_chunk("This standard specifies certification and testing requirements.")]
    assert looks_off_corpus("certification standard for mobile phone batteries", evidence) is True


def test_inflected_forms_count_as_grounded():
    evidence = [_chunk("Deformed steel bars shall conform to the tolerance on nominal mass.")]
    assert looks_off_corpus("tolerance for deformed bar", evidence) is False


def test_no_chunks_is_not_off_corpus():
    """Empty retrieval is a different condition, already handled by the
    prompt's no-evidence path."""
    assert looks_off_corpus("anything at all", []) is False
