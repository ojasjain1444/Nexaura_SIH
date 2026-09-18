"""
Indexing service tests — real chunking + real embedding model (marked
slow) against synthetic test documents processed through the real Phase 3
pipeline. Never real BIS content.
"""

from pathlib import Path

import pytest

from app.ingestion.pipeline import run_pipeline
from app.models.document_chunk import DocumentChunk
from app.models.standard_document import StandardDocument
from app.ocr.tesseract_provider import TesseractOCRProvider
from app.rag.index_document import IndexingError, index_document
from app.repositories.chunk_repository import ChunkRepository
from app.services.document_service import DocumentService

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _process_fixture(db_session, isolated_storage, filename: str) -> str:
    content = (FIXTURES_DIR / filename).read_bytes()
    service = DocumentService(db_session)
    document = service.register_upload(content, filename, "application/pdf", source_type="test")
    service.process_document(document.id, content)
    return document.id


@pytest.mark.slow
def test_indexing_a_completed_document_creates_chunks_with_embeddings(db_session, isolated_storage):
    document_id = _process_fixture(db_session, isolated_storage, "test_text.pdf")

    result = index_document(db_session, document_id)
    assert result.chunks_created > 0
    assert result.chunks_embedded == result.chunks_created

    chunks = ChunkRepository(db_session).get_by_document(document_id)
    assert len(chunks) == result.chunks_created
    for chunk in chunks:
        assert chunk.embedding_json is not None
        assert chunk.embedding_model == "intfloat/multilingual-e5-small"
        assert chunk.embedding_dimension == 384


def test_indexing_preserves_document_page_section_provenance(db_session, isolated_storage):
    from tests.test_embeddings import FakeEmbeddingProvider

    document_id = _process_fixture(db_session, isolated_storage, "test_text.pdf")
    index_document(db_session, document_id, embedding_provider=FakeEmbeddingProvider())

    chunks = ChunkRepository(db_session).get_by_document(document_id)
    assert all(c.document_id == document_id for c in chunks)
    assert all(c.page_number == 1 for c in chunks)
    # Different chunks correspond to different detected sections.
    sections = {c.section for c in chunks}
    assert "1" in sections or "2" in sections or "3" in sections


def test_indexing_uncompleted_document_raises(db_session, isolated_storage):
    from tests.test_embeddings import FakeEmbeddingProvider

    content = (FIXTURES_DIR / "test_text.pdf").read_bytes()
    service = DocumentService(db_session)
    document = service.register_upload(content, "test_text.pdf", "application/pdf", source_type="test")
    # Deliberately NOT calling process_document — status stays "uploaded".

    with pytest.raises(IndexingError, match="not 'completed'"):
        index_document(db_session, document.id, embedding_provider=FakeEmbeddingProvider())


def test_indexing_nonexistent_document_raises(db_session, isolated_storage):
    from tests.test_embeddings import FakeEmbeddingProvider

    with pytest.raises(IndexingError, match="not found"):
        index_document(db_session, "does-not-exist", embedding_provider=FakeEmbeddingProvider())


def test_reindexing_does_not_create_duplicate_chunks(db_session, isolated_storage):
    from tests.test_embeddings import FakeEmbeddingProvider

    document_id = _process_fixture(db_session, isolated_storage, "test_text.pdf")
    provider = FakeEmbeddingProvider()

    first_result = index_document(db_session, document_id, embedding_provider=provider)
    second_result = index_document(db_session, document_id, embedding_provider=provider)

    assert first_result.chunks_created == second_result.chunks_created
    chunks = ChunkRepository(db_session).get_by_document(document_id)
    assert len(chunks) == first_result.chunks_created  # not doubled


def test_indexing_empty_page_document_produces_zero_chunks_not_an_error(db_session, isolated_storage):
    from tests.test_embeddings import FakeEmbeddingProvider

    document_id = _process_fixture(db_session, isolated_storage, "test_empty.pdf")
    result = index_document(db_session, document_id, embedding_provider=FakeEmbeddingProvider())
    assert result.chunks_created == 0
    assert result.chunks_embedded == 0


def test_embedding_failure_during_indexing_raises_indexing_error(db_session, isolated_storage):
    from app.rag.embeddings import EmbeddingError

    class AlwaysFailingProvider:
        model_name = "failing-model"
        dimension = 8

        def embed_text(self, text):
            raise EmbeddingError("simulated failure")

        def embed_texts(self, texts):
            raise EmbeddingError("simulated failure")

    document_id = _process_fixture(db_session, isolated_storage, "test_text.pdf")
    with pytest.raises(IndexingError, match="Embedding failed"):
        index_document(db_session, document_id, embedding_provider=AlwaysFailingProvider())
