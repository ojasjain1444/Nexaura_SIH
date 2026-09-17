"""
bm25.py — BM25 Keyword Search Index

Project: Nexaura (SIH 2026 — SIH26107)

Builds and queries a BM25 keyword index over KnowledgeUnit records.

Supports:
    - Exact queries: "IS 1234"
    - Natural language: "galvanized steel pipe for buried water supply"

Indexed fields:
    - standard_number
    - title
    - scope
    - heading
    - keywords
    - product
    - application
    - material
    - technical_parameters
    - clause text

Index is serialized to disk and reloaded on startup.
"""

from __future__ import annotations

import logging
import os
import pickle
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Tokenizer
# =============================================================================

def tokenize(text: str) -> list[str]:
    """
    Tokenize text for BM25 indexing.

    Splits on non-alphanumeric characters, lowercases,
    removes very short tokens and common stop words.
    Preserves IS standard numbers (e.g. "IS456").
    """
    STOP_WORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at",
        "to", "for", "of", "with", "by", "from", "is", "are",
        "was", "were", "be", "been", "being", "have", "has", "had",
        "this", "that", "these", "those", "it", "its",
        "as", "at", "be", "by", "do", "he", "if", "in", "me",
        "my", "no", "not", "of", "on", "or", "so", "to", "up",
        "we", "he", "it",
    }

    # Normalize whitespace
    text = text.lower().strip()

    # Split on whitespace and punctuation (keep alphanumeric and dots for IS numbers)
    tokens = re.findall(r"[a-z0-9μµ°%²³/]+(?:\.[a-z0-9]+)*", text)

    # Filter stop words and very short tokens
    tokens = [t for t in tokens if len(t) > 1 and t not in STOP_WORDS]

    return tokens


# =============================================================================
# Fallback BM25 Implementation
# =============================================================================

class SimpleBM25Okapi:
    """Zero-dependency fallback implementation of BM25Okapi."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        import math
        from collections import Counter

        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.doc_len = [len(doc) for doc in corpus]
        self.avgdl = sum(self.doc_len) / self.corpus_size if self.corpus_size > 0 else 1.0
        self.doc_freqs = [Counter(doc) for doc in corpus]

        df = Counter()
        for doc in corpus:
            df.update(set(doc))

        self.idf = {}
        for word, freq in df.items():
            self.idf[word] = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        scores = [0.0] * self.corpus_size
        for token in query_tokens:
            if token not in self.idf:
                continue
            idf_val = self.idf[token]
            for i, freqs in enumerate(self.doc_freqs):
                f = freqs.get(token, 0)
                if f > 0:
                    denom = f + self.k1 * (1.0 - self.b + self.b * (self.doc_len[i] / self.avgdl))
                    scores[i] += idf_val * (f * (self.k1 + 1.0)) / denom
        return scores


class _BM25Unpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if module == "rank_bm25" and name == "BM25Okapi":
            try:
                from rank_bm25 import BM25Okapi
                return BM25Okapi
            except ImportError:
                return SimpleBM25Okapi
        return super().find_class(module, name)


# =============================================================================
# BM25 Index
# =============================================================================

class BM25Index:
    """
    BM25 keyword search index for BIS Knowledge Units.

    Built using rank_bm25 (BM25Okapi implementation) or built-in SimpleBM25Okapi fallback.
    Supports incremental updates and disk persistence.
    """

    def __init__(self, index_path: Optional[Path] = None) -> None:
        """
        Args:
            index_path: Path to save/load the serialized index.
        """
        self.index_path = Path(index_path) if index_path else None
        self._bm25 = None
        self._doc_ids: list[str] = []          # knowledge_unit_id per document
        self._doc_metadata: list[dict] = []    # lightweight metadata per doc
        self._corpus: list[list[str]] = []     # tokenized documents

    # -------------------------------------------------------------------------
    # Build
    # -------------------------------------------------------------------------

    def build(self, knowledge_units: list) -> None:
        """
        Build BM25 index from a list of KnowledgeUnits.

        Args:
            knowledge_units: List of KnowledgeUnit objects.
        """
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            BM25Okapi = SimpleBM25Okapi

        logger.info("Building BM25 index from %d knowledge units...", len(knowledge_units))

        self._doc_ids = []
        self._doc_metadata = []
        self._corpus = []

        for ku in knowledge_units:
            search_text = ku.search_text or ku.clean_text or ku.text or ""
            tokens = tokenize(search_text)
            if not tokens:
                tokens = ["empty"]

            self._corpus.append(tokens)
            self._doc_ids.append(ku.id)
            self._doc_metadata.append({
                "id":              ku.id,
                "standard_number": ku.standard_number,
                "title":           ku.title,
                "clause":          ku.clause,
                "heading":         ku.heading,
                "page_start":      ku.page_start,
                "source_pdf":      ku.source_pdf,
                "content_type":    ku.content_type,
            })

        self._bm25 = BM25Okapi(self._corpus)
        logger.info(
            "BM25 index built: %d documents, vocabulary_size=%d",
            len(self._corpus),
            len(self._bm25.idf) if hasattr(self._bm25, "idf") else 0,
        )

    def build_from_texts(self, doc_ids: list[str], texts: list[str], metadatas: list[dict]) -> None:
        """
        Build BM25 index from raw texts (alternative to knowledge units).

        Args:
            doc_ids: List of document IDs (knowledge_unit_id).
            texts: Corresponding search texts.
            metadatas: Corresponding metadata dicts.
        """
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as e:
            raise ImportError("rank-bm25 required: pip install rank-bm25") from e

        self._doc_ids = doc_ids
        self._doc_metadata = metadatas
        self._corpus = [tokenize(t) or ["empty"] for t in texts]
        self._bm25 = BM25Okapi(self._corpus)

        logger.info("BM25 index built from %d texts", len(doc_ids))

    # -------------------------------------------------------------------------
    # Query
    # -------------------------------------------------------------------------

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        Search the BM25 index.

        Args:
            query: Search query (natural language or exact term).
            top_k: Number of top results to return.

        Returns:
            List of result dicts sorted by BM25 score descending.
        """
        if self._bm25 is None:
            logger.warning("BM25 index not built. Call build() first.")
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            logger.warning("Query tokenized to empty: %s", query)
            return []

        scores = self._bm25.get_scores(query_tokens)

        # Get top-K indices
        import numpy as np
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score <= 0:
                break
            results.append({
                "rank":       len(results) + 1,
                "score":      score,
                "id":         self._doc_ids[idx],
                "metadata":   self._doc_metadata[idx],
            })

        return results

    def get_scores(self, query: str) -> list[float]:
        """Get raw BM25 scores for all documents."""
        if self._bm25 is None:
            return []
        tokens = tokenize(query)
        if not tokens:
            return [0.0] * len(self._doc_ids)
        return self._bm25.get_scores(tokens).tolist()

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def save(self, path: Optional[Path] = None) -> Path:
        """
        Serialize and save the BM25 index to disk.

        Args:
            path: Output path. Uses self.index_path if not provided.

        Returns:
            Path where the index was saved.
        """
        save_path = Path(path) if path else self.index_path
        if save_path is None:
            raise ValueError("No index_path specified for saving BM25 index.")

        save_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "bm25":     self._bm25,
            "doc_ids":  self._doc_ids,
            "metadata": self._doc_metadata,
            "corpus":   self._corpus,
        }
        with open(save_path, "wb") as f:
            pickle.dump(data, f)
        logger.info("BM25 index saved: %s (%d docs)", save_path, len(self._doc_ids))
        return save_path

    def load(self, path: Optional[Path] = None) -> bool:
        """
        Load a serialized BM25 index from disk.

        Args:
            path: Index file path. Uses self.index_path if not provided.

        Returns:
            True if loaded successfully, False if file not found.
        """
        load_path = Path(path) if path else self.index_path
        if load_path is None or not load_path.exists():
            logger.info("BM25 index not found at %s — will build fresh", load_path)
            return False

        with open(load_path, "rb") as f:
            data = _BM25Unpickler(f).load()

        self._bm25     = data["bm25"]
        self._doc_ids  = data["doc_ids"]
        self._doc_metadata = data["metadata"]
        self._corpus   = data.get("corpus", [])

        logger.info("BM25 index loaded: %s (%d docs)", load_path, len(self._doc_ids))
        return True

    @property
    def is_built(self) -> bool:
        """True if index has been built or loaded."""
        return self._bm25 is not None

    @property
    def doc_count(self) -> int:
        """Number of documents in the index."""
        return len(self._doc_ids)
