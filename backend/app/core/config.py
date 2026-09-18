"""
Central configuration for the BIS Sahayak backend.

Every setting has a safe default so the app can start with zero
configuration. Provider credentials (LLM, embeddings, OCR, STT, TTS) are
intentionally optional here — Phase 1 has no code that calls any of them,
and future phases must degrade gracefully (feature disabled) rather than
fail startup when a given provider isn't configured.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Service identity ---
    service_name: str = "bis-sahayak-api"
    environment: str = "development"

    # --- Database ---
    # SQLite by default for local development (see docs/ARCHITECTURE.md for
    # why: no PostgreSQL client/server is installed on the reference dev
    # machine for this project). The URL is PostgreSQL-compatible in shape
    # so switching later is a config change, not a code change, as long as
    # Postgres-only column types are avoided until that migration happens.
    database_url: str = "sqlite:///./bis_sahayak.db"

    # --- CORS ---
    # Comma-separated list of allowed origins. Defaults to exactly the Vite
    # dev server origin — never a wildcard by default.
    cors_origins: str = "http://localhost:5173"

    # --- AI providers ---
    # Phase 5: llm_provider is None by default -> chat generation returns a
    # structured LLM_NOT_CONFIGURED error rather than a fabricated answer.
    # Set to "mock" for development (explicitly labelled, never confused
    # with real output), "anthropic" (requires llm_api_key) for a paid
    # cloud provider, or "ollama" (Phase 7 — requires a locally running
    # Ollama instance, no API key) for a local/open-source model. None of
    # these is auto-selected as a default; see app/llm/provider.py.
    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None  # None = provider's own default
    # Phase 7: base URL of a locally running Ollama server. Only read when
    # llm_provider == "ollama". No API key involved — Ollama is local.
    ollama_base_url: str = "http://localhost:11434"
    # Phase 4: "local" (default) uses sentence-transformers with no API key.
    # See app/rag/embeddings.py for the concrete provider implementations.
    embedding_provider: str | None = "local"
    embedding_model: str | None = None  # None = provider's own default (see LocalEmbeddingProvider)
    embedding_api_key: str | None = None
    ocr_provider: str | None = None
    stt_provider: str | None = None
    tts_provider: str | None = None

    # External standard fallback (app/product/external_standard_fallback.py):
    # when local retrieval finds nothing relevant for a product, search
    # Internet Archive's public Indian Standards index and ingest a real
    # match on the spot. Defaults to disabled — a live network call during
    # a chat turn (or, worse, during an automated test run with no network
    # access) must be something a developer explicitly opts into, never
    # something that fires by default. Set EXTERNAL_STANDARD_FALLBACK_ENABLED=true
    # to turn it on for a real deployment.
    external_standard_fallback_enabled: bool = False

    # --- Storage ---
    storage_path: str = "./data"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — read once per process."""
    return Settings()
