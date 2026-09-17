"""
embedding_service.py — Configurable Embedding Provider

Project: Nexaura (SIH 2026 — SIH26107)

Provides embeddings for KnowledgeUnit.search_text.

Two implementations:
    1. SentenceTransformerProvider — local, offline, default
       Model: all-MiniLM-L6-v2 (384-dim)
    2. GoogleEmbeddingProvider    — online, requires GEMINI_API_KEY
       Model: text-embedding-004

The provider is selected from config.yaml:
    embeddings.provider: "sentence_transformers" | "google"

NEVER embed entire PDFs — only semantic units (clauses, scope, etc.)
Embeddings are generated AFTER cleaning and validation.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# Abstract Base
# =============================================================================

class EmbeddingProvider(ABC):
    """Abstract embedding provider interface."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension size."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (same length as input).
        """

    def embed_one(self, text: str) -> list[float]:
        """Embed a single text string."""
        results = self.embed([text])
        return results[0] if results else []


# =============================================================================
# Sentence Transformers (local, offline)
# =============================================================================

class SentenceTransformerProvider(EmbeddingProvider):
    """
    Local embedding provider using sentence-transformers.

    Fully offline — no API calls.
    Default model: all-MiniLM-L6-v2 (384 dimensions, fast, good quality).

    Other recommended models:
        - all-mpnet-base-v2 (768 dim, higher quality)
        - paraphrase-multilingual-MiniLM-L12-v2 (for multilingual)
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        normalize: bool = True,
        device: Optional[str] = None,
        batch_size: int = 32,
    ) -> None:
        """
        Args:
            model_name: Sentence transformer model name or path.
            normalize: If True, normalize vectors to unit length.
            device: 'cpu', 'cuda', or None (auto-detect).
            batch_size: Batch size for encoding.
        """
        self.model_name = model_name
        self.normalize = normalize
        self.device = device
        self.batch_size = batch_size
        self._model = None

        logger.info("SentenceTransformerProvider configured: model=%s", model_name)

    @property
    def dimension(self) -> int:
        model = self._get_model()
        return model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        if not texts:
            return []

        model = self._get_model()

        # Filter empty texts
        cleaned = [t if t and t.strip() else " " for t in texts]

        logger.debug("Embedding %d texts with %s", len(cleaned), self.model_name)

        embeddings = model.encode(
            cleaned,
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize,
            show_progress_bar=len(cleaned) > 50,
        )

        return embeddings.tolist()

    def _get_model(self):
        """Lazy-load the sentence transformer model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers required: pip install sentence-transformers"
                ) from e

            logger.info("Loading SentenceTransformer model: %s", self.model_name)
            kwargs: dict = {}
            if self.device:
                kwargs["device"] = self.device
            self._model = SentenceTransformer(self.model_name, **kwargs)
            logger.info(
                "Model loaded: dim=%d", self._model.get_sentence_embedding_dimension()
            )
        return self._model


# =============================================================================
# Google Embedding API (online)
# =============================================================================

class GoogleEmbeddingProvider(EmbeddingProvider):
    """
    Google embedding provider using text-embedding-004.

    Requires GEMINI_API_KEY environment variable.
    """

    def __init__(
        self,
        model_name: str = "text-embedding-004",
        api_key: Optional[str] = None,
        task_type: str = "RETRIEVAL_DOCUMENT",
        batch_size: int = 100,
    ) -> None:
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.task_type = task_type
        self.batch_size = batch_size
        self._dim = 768  # text-embedding-004 default

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be set for GoogleEmbeddingProvider")

        logger.info("GoogleEmbeddingProvider configured: model=%s", model_name)

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using Google's API."""
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise ImportError("google-generativeai required") from e

        if not texts:
            return []

        genai.configure(api_key=self.api_key)
        all_embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            result = genai.embed_content(
                model=f"models/{self.model_name}",
                content=batch,
                task_type=self.task_type,
            )
            all_embeddings.extend(result["embedding"])

        return all_embeddings


# =============================================================================
# Embedding Service (high-level)
# =============================================================================

class EmbeddingService:
    """
    High-level embedding service for the Nexaura pipeline.

    Wraps the configured provider and adds:
    - Batch processing with progress logging
    - Empty text handling
    - Error recovery
    """

    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider
        logger.info(
            "EmbeddingService ready: provider=%s dim=%d",
            type(provider).__name__, provider.dimension,
        )

    @property
    def dimension(self) -> int:
        return self.provider.dimension

    def embed_knowledge_units(
        self,
        knowledge_units: list,
        batch_size: int = 32,
    ) -> list[list[float]]:
        """
        Generate embeddings for a list of KnowledgeUnits.

        Uses search_text for embedding — the rich combined text
        (title + scope + heading + keywords + products + clause text).

        Args:
            knowledge_units: List of KnowledgeUnit objects.
            batch_size: Processing batch size.

        Returns:
            List of embedding vectors (same length as knowledge_units).
        """
        texts = [
            ku.search_text or ku.clean_text or ku.text or ""
            for ku in knowledge_units
        ]
        return self.embed_texts(texts, batch_size=batch_size)

    def embed_texts(
        self,
        texts: list[str],
        batch_size: int = 32,
    ) -> list[list[float]]:
        """
        Generate embeddings for a list of text strings.

        Args:
            texts: List of text strings.
            batch_size: Processing batch size.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                embeddings = self.provider.embed(batch)
                all_embeddings.extend(embeddings)
            except Exception as exc:
                logger.error(
                    "Embedding failed for batch %d: %s — using zeros",
                    i // batch_size, exc,
                )
                # Never lose data — use zero vectors for failed batches
                zeros = [[0.0] * self.provider.dimension] * len(batch)
                all_embeddings.extend(zeros)

            if len(texts) > 100 and i % (batch_size * 10) == 0:
                logger.info(
                    "Embedding progress: %d/%d", i + len(batch), len(texts)
                )

        return all_embeddings

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query."""
        results = self.provider.embed([query])
        return results[0] if results else [0.0] * self.provider.dimension


# =============================================================================
# Factory function
# =============================================================================

def create_embedding_service(
    provider: str = "sentence_transformers",
    model: Optional[str] = None,
    **kwargs,
) -> EmbeddingService:
    """
    Factory function to create an EmbeddingService from config.

    Args:
        provider: "sentence_transformers" | "google"
        model: Model name (uses defaults if None)
        **kwargs: Additional arguments passed to the provider

    Returns:
        EmbeddingService instance
    """
    if provider == "google":
        embedding_provider = GoogleEmbeddingProvider(
            model_name=model or "text-embedding-004",
            **kwargs,
        )
    else:
        # Default: local sentence transformers
        embedding_provider = SentenceTransformerProvider(
            model_name=model or "all-MiniLM-L6-v2",
            **kwargs,
        )

    return EmbeddingService(embedding_provider)
