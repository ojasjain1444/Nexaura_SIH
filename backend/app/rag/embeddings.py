"""
Embedding provider abstraction.

Nothing outside this module imports sentence_transformers directly — the
rest of the app only ever talks to the `EmbeddingProvider` protocol, so a
future cloud embedding provider (OpenAI, Cohere, etc.) is a new class
implementing the same protocol, not a rewrite of chunking/indexing/
retrieval code.

Provider selection is via configuration (EMBEDDING_PROVIDER), defaulting to
"local" — which requires no API key and no network access at inference
time (the model is downloaded once and cached; see docs/RAG_RETRIEVAL.md).
"""

import threading
from typing import Protocol

from app.core.config import get_settings

LOCAL_MODEL_NAME = "intfloat/multilingual-e5-small"
LOCAL_MODEL_DIMENSION = 384


class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int

    def embed_text(self, text: str) -> list[float]: ...
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingError(Exception):
    pass


class LocalEmbeddingProvider:
    """
    sentence-transformers-backed provider using intfloat/multilingual-e5-small
    (384 dimensions). See docs/RAG_RETRIEVAL.md for why this model was
    selected and how it was tested (load time, encode time, and a
    cross-lingual similarity sanity check — not a rigorous benchmark).

    The underlying model is loaded exactly once per process (module-level
    singleton, guarded by a lock) — never per request, per the explicit
    requirement not to reload the embedding model on every call. Actually
    measured on this machine: ~67s cold (first download+load),
    ~10.6s warm (cached weights, still has to load into memory once).
    """

    model_name = LOCAL_MODEL_NAME
    dimension = LOCAL_MODEL_DIMENSION

    _model = None
    _lock = threading.Lock()

    def _get_model(self):
        if LocalEmbeddingProvider._model is None:
            with LocalEmbeddingProvider._lock:
                if LocalEmbeddingProvider._model is None:
                    try:
                        from sentence_transformers import SentenceTransformer
                    except ImportError as exc:
                        raise EmbeddingError(
                            "sentence-transformers is not installed. Run `pip install -r requirements.txt`."
                        ) from exc
                    # Forced onto CPU: sentence-transformers otherwise
                    # auto-selects the Apple MPS GPU backend on macOS,
                    # which was observed to crash the entire backend
                    # process (MTLCommandBufferStatusCommitted assertion
                    # failure in PyTorch's MPS driver) under back-to-back
                    # encode calls from concurrent document uploads. This
                    # model is small enough that CPU inference is fast
                    # enough for this app's local, low-volume usage, and
                    # crash-proof is worth more here than GPU speed.
                    LocalEmbeddingProvider._model = SentenceTransformer(LOCAL_MODEL_NAME, device="cpu")
        return LocalEmbeddingProvider._model

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        try:
            # E5 models require a "query: " or "passage: " instruction
            # prefix for good retrieval quality — this is a documented
            # requirement of this specific model family, not a general
            # embedding convention. Chunks are always indexed as
            # "passage: "; queries are prefixed by the caller (see
            # retrieval.py) with "query: " instead.
            vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        except Exception as exc:
            raise EmbeddingError(f"Embedding failed: {exc}") from exc
        return [vector.tolist() for vector in vectors]


def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    provider = settings.embedding_provider or "local"
    if provider == "local":
        return LocalEmbeddingProvider()
    raise EmbeddingError(
        f"Unknown EMBEDDING_PROVIDER '{provider}'. Only 'local' is implemented in this phase."
    )
