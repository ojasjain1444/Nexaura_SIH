"""
config_loader.py — Centralised Configuration Loader

Project: Nexaura (SIH 2026 — SIH26107)

Loads config/config.yaml and resolves ${ENV_VAR} placeholders.
Provides a typed config object used across all nexaura modules.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Resolves ${VAR_NAME} patterns in YAML values
ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve_env(value: Any) -> Any:
    """Recursively resolve ${ENV_VAR} placeholders in strings."""
    if isinstance(value, str):
        def replacer(match: re.Match) -> str:
            var = match.group(1)
            resolved = os.environ.get(var, "")
            if not resolved:
                logger.debug("Env var not set: %s", var)
            return resolved
        return ENV_PATTERN.sub(replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env(item) for item in value]
    return value


class NexauraConfig:
    """
    Typed configuration object for the Nexaura pipeline.

    All values read from config/config.yaml with environment variable
    substitution. Falls back to sensible defaults if config file not found.
    """

    def __init__(self, raw: dict) -> None:
        self._raw = raw
        nexaura = raw.get("nexaura", {})

        # Gemini
        gemini = nexaura.get("gemini", {})
        self.gemini_model          = gemini.get("model", "gemini-2.0-flash")
        self.gemini_temperature    = float(gemini.get("temperature", 0.0))
        self.gemini_max_retries    = int(gemini.get("max_retries", 5))
        self.gemini_backoff_base   = float(gemini.get("retry_backoff_base", 2.0))
        self.gemini_batch_size     = int(gemini.get("batch_size", 5))
        self.gemini_max_concurrent = int(gemini.get("max_concurrent_requests", 2))

        # PDF processing
        pdf = nexaura.get("pdf", {})
        self.pdf_text_threshold = int(pdf.get("text_threshold", 50))
        self.pdf_force_gemini   = bool(pdf.get("force_gemini", False))

        # Embeddings
        emb = nexaura.get("embeddings", {})
        self.embedding_provider  = emb.get("provider", "sentence_transformers")
        self.embedding_model     = emb.get("model", "all-MiniLM-L6-v2")
        self.embedding_batch_size= int(emb.get("batch_size", 32))

        # Qdrant
        qdrant = nexaura.get("qdrant", {})
        self.qdrant_url        = qdrant.get("url", "http://localhost:6333")
        self.qdrant_api_key    = qdrant.get("api_key", "") or None
        self.qdrant_collection = qdrant.get("collection", "bis_knowledge")
        self.qdrant_vector_size= int(qdrant.get("vector_size", 384))

        # PostgreSQL (legacy)
        postgres = nexaura.get("postgres", {})
        self.postgres_url = postgres.get("url", "")

        # MongoDB (KnowledgeBase)
        mongodb = nexaura.get("mongodb", {})
        self.mongo_url = mongodb.get("url", "mongodb://localhost:27017")
        self.mongo_db_name = mongodb.get("db_name", "KnowledgeBase")

        # Search weights
        search = nexaura.get("search", {})
        self.search_top_k = int(search.get("top_k", 10))
        weights = search.get("weights", {})
        self.search_weights = {
            "semantic":            float(weights.get("semantic", 0.40)),
            "keyword":             float(weights.get("keyword", 0.20)),
            "scope":               float(weights.get("scope", 0.15)),
            "product_application": float(weights.get("product_application", 0.10)),
            "technical":           float(weights.get("technical", 0.10)),
            "metadata":            float(weights.get("metadata", 0.05)),
        }

        # Processing
        proc = nexaura.get("processing", {})
        self.workers       = int(proc.get("workers", 4))
        self.resume        = bool(proc.get("resume", True))
        self.checkpoint_dir= Path(proc.get("checkpoint_dir", "nexaura/data/checkpoints"))

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from raw config by dotted key path."""
        parts = key.split(".")
        current = self._raw
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part, default)
            else:
                return default
        return current


def load_config(config_path: Optional[Path] = None) -> NexauraConfig:
    """
    Load and return the Nexaura configuration.

    Args:
        config_path: Path to config.yaml. Auto-discovers from project root.

    Returns:
        NexauraConfig instance with all settings resolved.
    """
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed — using defaults")
        return NexauraConfig({})

    # Auto-discover config file
    if config_path is None:
        # Search from this file's location upward
        search_dirs = [
            Path(__file__).resolve().parent.parent.parent.parent,  # project root
            Path.cwd(),
            Path.cwd().parent,
        ]
        for d in search_dirs:
            candidate = d / "config" / "config.yaml"
            if candidate.exists():
                config_path = candidate
                break

    if config_path is None or not Path(config_path).exists():
        logger.warning("config.yaml not found — using all defaults and env vars")
        raw: dict = {}
    else:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        raw = _resolve_env(raw)
        logger.info("Config loaded from: %s", config_path)

    return NexauraConfig(raw)


# Module-level singleton (lazy)
_config: Optional[NexauraConfig] = None


def get_config() -> NexauraConfig:
    """Get the global config singleton (loads on first call)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
