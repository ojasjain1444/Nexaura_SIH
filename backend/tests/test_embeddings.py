"""
Embedding provider tests.

Most tests here use a lightweight FakeEmbeddingProvider (deterministic,
instant) so the suite doesn't pay the real model's ~10s load time on every
run. test_local_embedding_provider_real_model actually loads and runs the
real sentence-transformers model once, to prove the real integration
genuinely works (not just the abstraction around it).
"""

import pytest

from app.rag.embeddings import EmbeddingError, LocalEmbeddingProvider, get_embedding_provider


class FakeEmbeddingProvider:
    """Deterministic stand-in for tests that need an EmbeddingProvider but
    don't need to verify the real model — hashes text into a fixed-size
    vector so identical text always yields identical vectors."""

    model_name = "fake-test-model"
    dimension = 8

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            seed = sum(ord(c) for c in text)
            vectors.append([((seed + i) % 100) / 100.0 for i in range(self.dimension)])
        return vectors


def test_fake_provider_is_deterministic():
    provider = FakeEmbeddingProvider()
    assert provider.embed_text("hello") == provider.embed_text("hello")


def test_fake_provider_different_text_different_vector():
    provider = FakeEmbeddingProvider()
    assert provider.embed_text("hello") != provider.embed_text("goodbye")


def test_embed_texts_empty_list_returns_empty():
    provider = FakeEmbeddingProvider()
    assert provider.embed_texts([]) == []


def test_get_embedding_provider_defaults_to_local():
    provider = get_embedding_provider()
    assert isinstance(provider, LocalEmbeddingProvider)
    assert provider.model_name == "intfloat/multilingual-e5-small"
    assert provider.dimension == 384


@pytest.mark.slow
def test_local_embedding_provider_real_model():
    """Actually loads and runs the real model — verified to work in
    development (see docs/RAG_RETRIEVAL.md), kept as a real (not mocked)
    integration test here."""
    provider = LocalEmbeddingProvider()
    vector = provider.embed_text("query: test")
    assert len(vector) == 384
    assert all(isinstance(v, float) for v in vector)


@pytest.mark.slow
def test_local_embedding_provider_batch():
    provider = LocalEmbeddingProvider()
    vectors = provider.embed_texts(["passage: first text", "passage: second text"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    assert vectors[0] != vectors[1]
