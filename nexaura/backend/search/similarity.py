"""
similarity.py — Feature-Based Similarity Engine

Project: Nexaura (SIH 2026 — SIH26107)

The Nexaura chatbot uses multi-dimensional similarity search.

For each user query:
1. Extract query features (product, material, application, parameters)
2. Run in parallel:
   - Vector similarity (Qdrant)
   - BM25 keyword similarity
   - Scope matching
   - Product/application matching
   - Technical feature matching
   - Metadata matching
3. Combine with configurable weights
4. Return top-K with per-component scores

Default weights (configurable via config.yaml):
    semantic:            0.40
    keyword:             0.20
    scope:               0.15
    product_application: 0.10
    technical:           0.10
    metadata:            0.05
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Result Model
# =============================================================================

@dataclass
class SimilarityResult:
    """A single ranked similarity result."""

    # Identity
    knowledge_unit_id: str
    standard_number: str
    title: Optional[str]
    edition: Optional[str]
    clause: str
    heading: Optional[str]
    page_start: int
    source_pdf: str
    content_type: str

    # Scores
    final_score: float
    semantic_score: float = 0.0
    keyword_score: float  = 0.0
    scope_score: float    = 0.0
    product_score: float  = 0.0
    technical_score: float= 0.0
    metadata_score: float = 0.0

    # Matched features (for explanation)
    matched_products: list[str] = field(default_factory=list)
    matched_materials: list[str] = field(default_factory=list)
    matched_applications: list[str] = field(default_factory=list)
    matched_params: list[str] = field(default_factory=list)

    # Payload from vector DB
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "standard":        self.standard_number,
            "title":           self.title,
            "edition":         self.edition,
            "clause":          self.clause,
            "heading":         self.heading,
            "page":            self.page_start,
            "source_pdf":      self.source_pdf,
            "content_type":    self.content_type,
            "score":           round(self.final_score, 4),
            "semantic_score":  round(self.semantic_score, 4),
            "keyword_score":   round(self.keyword_score, 4),
            "scope_score":     round(self.scope_score, 4),
            "product_score":   round(self.product_score, 4),
            "technical_score": round(self.technical_score, 4),
            "metadata_score":  round(self.metadata_score, 4),
            "matched_features": {
                "products":      self.matched_products,
                "materials":     self.matched_materials,
                "applications":  self.matched_applications,
                "parameters":    self.matched_params,
            },
        }


# =============================================================================
# Query Feature Extractor
# =============================================================================

class QueryFeatureExtractor:
    """
    Extracts structured features from a user query string.

    Example:
        Query: "galvanized steel pipe for buried water supply coating thickness"
        Features:
            product:     ["galvanized steel pipe"]
            material:    ["steel", "zinc"]
            application: ["buried water supply"]
            property:    ["coating thickness"]
    """

    PRODUCTS = [
        "galvanized pipe", "galvanized steel", "steel pipe", "cast iron pipe",
        "cement", "concrete", "reinforced concrete", "steel bar", "wire rope",
        "valve", "fitting", "cable", "bolt", "nut", "tile", "brick",
    ]
    MATERIALS = [
        "steel", "iron", "zinc", "aluminium", "copper", "brass", "concrete",
        "cement", "rubber", "plastic", "glass", "wood", "timber", "bitumen",
    ]
    APPLICATIONS = [
        "water supply", "drinking water", "sewage", "drainage", "irrigation",
        "gas supply", "structural", "building", "construction", "underground",
        "buried", "submerged", "electrical", "highway", "bridge", "fire fighting",
    ]
    PROPERTIES = [
        "coating thickness", "tensile strength", "yield strength", "elongation",
        "hardness", "impact strength", "density", "chemical composition",
        "compressive strength", "flexural strength", "pressure", "temperature",
        "dimension", "tolerance", "weight",
    ]

    def extract(self, query: str) -> dict[str, list[str]]:
        """Extract feature categories from a query string."""
        query_lower = query.lower()
        features: dict[str, list[str]] = {
            "product": [],
            "material": [],
            "application": [],
            "property": [],
        }

        for p in self.PRODUCTS:
            if p.lower() in query_lower:
                features["product"].append(p)

        for m in self.MATERIALS:
            if re.search(r"\b" + re.escape(m) + r"\b", query_lower):
                features["material"].append(m)

        for a in self.APPLICATIONS:
            if a.lower() in query_lower:
                features["application"].append(a)

        for prop in self.PROPERTIES:
            if prop.lower() in query_lower:
                features["property"].append(prop)

        return features


# =============================================================================
# Similarity Engine
# =============================================================================

class SimilarityEngine:
    """
    Multi-dimensional similarity search engine for Nexaura.

    Combines:
        - Semantic similarity (vector search via Qdrant)
        - Keyword similarity (BM25)
        - Scope similarity (scope-specific vector search)
        - Product/application matching (feature matching)
        - Technical feature matching (parameter names)
        - Metadata matching (standard number exact match)

    All weights are configurable.
    """

    DEFAULT_WEIGHTS = {
        "semantic":            0.40,
        "keyword":             0.20,
        "scope":               0.15,
        "product_application": 0.10,
        "technical":           0.10,
        "metadata":            0.05,
    }

    def __init__(
        self,
        embedding_service,    # EmbeddingService
        qdrant_manager,       # QdrantManager
        bm25_index,           # BM25Index
        weights: Optional[dict] = None,
        top_k: int = 10,
        min_score: float = 0.20,
    ) -> None:
        self.embedding_service = embedding_service
        self.qdrant = qdrant_manager
        self.bm25 = bm25_index
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.top_k = top_k
        self.min_score = min_score
        self.query_extractor = QueryFeatureExtractor()

        logger.info(
            "SimilarityEngine ready: weights=%s top_k=%d",
            self.weights, self.top_k,
        )

    def search(self, query: str, top_k: Optional[int] = None) -> list[SimilarityResult]:
        """
        Perform feature-based similarity search.

        Args:
            query: User query string.
            top_k: Number of results (overrides default).

        Returns:
            List of SimilarityResult sorted by final_score descending.
        """
        k = top_k or self.top_k
        logger.info("Similarity search: query=%s top_k=%d", query[:80], k)

        # Step 1: Extract query features
        query_features = self.query_extractor.extract(query)
        logger.debug("Query features: %s", query_features)

        # Step 2: Semantic search (Qdrant)
        query_vector = self.embedding_service.embed_query(query)
        vector_results = self._vector_search(query_vector, k=k * 3)

        # Step 3: BM25 search
        bm25_results = self._bm25_search(query, k=k * 3)

        # Step 4: Merge candidate sets
        candidates = self._merge_candidates(vector_results, bm25_results)

        # Step 5: Score each candidate on all dimensions
        scored = []
        for candidate_id, payload, semantic_score in candidates:
            result = self._score_candidate(
                candidate_id, payload, semantic_score,
                query, query_features, bm25_results,
            )
            if result.final_score >= self.min_score:
                scored.append(result)

        # Step 6: Sort by final score
        scored.sort(key=lambda r: r.final_score, reverse=True)
        top_results = scored[:k]

        # Log results
        logger.info("Similarity search returned %d results", len(top_results))
        for i, r in enumerate(top_results[:3]):
            logger.info(
                "  [%d] %s %s | score=%.3f (sem=%.3f kw=%.3f prod=%.3f)",
                i + 1, r.standard_number, r.clause,
                r.final_score, r.semantic_score, r.keyword_score, r.product_score,
            )

        return top_results

    # -------------------------------------------------------------------------
    # Component searches
    # -------------------------------------------------------------------------

    def _vector_search(
        self, vector: list[float], k: int
    ) -> list[tuple[str, dict, float]]:
        """Run semantic vector search in Qdrant."""
        try:
            results = self.qdrant.search(query_vector=vector, top_k=k)
            return [
                (r["payload"].get("knowledge_unit_id", str(r["id"])),
                 r["payload"],
                 r["score"])
                for r in results
            ]
        except Exception as exc:
            logger.error("Vector search failed: %s", exc)
            return []

    def _bm25_search(self, query: str, k: int) -> dict[str, float]:
        """Run BM25 search. Returns {doc_id: score} mapping."""
        if not self.bm25.is_built:
            return {}
        try:
            results = self.bm25.search(query, top_k=k)
            # Normalize BM25 scores to [0, 1]
            if not results:
                return {}
            max_score = max(r["score"] for r in results) or 1.0
            return {r["id"]: r["score"] / max_score for r in results}
        except Exception as exc:
            logger.error("BM25 search failed: %s", exc)
            return {}

    def _merge_candidates(
        self,
        vector_results: list[tuple[str, dict, float]],
        bm25_results: dict[str, float],
    ) -> list[tuple[str, dict, float]]:
        """Merge vector and BM25 candidates into a unified set."""
        seen: dict[str, tuple[str, dict, float]] = {}

        # Add vector results
        for doc_id, payload, score in vector_results:
            seen[doc_id] = (doc_id, payload, score)

        # Add BM25-only results (payload will be empty — OK for scoring)
        for doc_id in bm25_results:
            if doc_id not in seen:
                seen[doc_id] = (doc_id, {}, 0.0)

        return list(seen.values())

    # -------------------------------------------------------------------------
    # Scoring
    # -------------------------------------------------------------------------

    def _score_candidate(
        self,
        candidate_id: str,
        payload: dict,
        semantic_score: float,
        query: str,
        query_features: dict,
        bm25_scores: dict[str, float],
    ) -> SimilarityResult:
        """Score a candidate on all similarity dimensions."""

        # Component 1: Semantic score (from Qdrant)
        sem_score = semantic_score

        # Component 2: Keyword score (from BM25)
        kw_score = bm25_scores.get(candidate_id, 0.0)

        # Component 3: Scope score (boost if content_type == "scope")
        scope_score = 0.0
        if payload.get("content_type") == "scope":
            scope_score = sem_score * 1.1  # slight boost for scope clauses

        # Component 4: Product/Application matching
        prod_score, matched_products, matched_apps = self._score_product_application(
            payload, query_features
        )

        # Component 5: Technical feature matching
        tech_score, matched_params = self._score_technical(payload, query_features)

        # Component 6: Metadata matching (exact IS number)
        meta_score = self._score_metadata(payload, query)

        # Weighted combination
        w = self.weights
        final = (
            w.get("semantic", 0.40)            * sem_score
            + w.get("keyword", 0.20)           * kw_score
            + w.get("scope", 0.15)             * scope_score
            + w.get("product_application", 0.10) * prod_score
            + w.get("technical", 0.10)         * tech_score
            + w.get("metadata", 0.05)          * meta_score
        )

        return SimilarityResult(
            knowledge_unit_id=candidate_id,
            standard_number=payload.get("standard_number", "unknown"),
            title=payload.get("title"),
            edition=payload.get("edition"),
            clause=payload.get("clause", ""),
            heading=payload.get("heading"),
            page_start=payload.get("page_start", 0),
            source_pdf=payload.get("source_pdf", ""),
            content_type=payload.get("content_type", "clause"),
            final_score=min(final, 1.0),
            semantic_score=sem_score,
            keyword_score=kw_score,
            scope_score=scope_score,
            product_score=prod_score,
            technical_score=tech_score,
            metadata_score=meta_score,
            matched_products=matched_products,
            matched_applications=matched_apps,
            matched_params=matched_params,
            payload=payload,
        )

    def _score_product_application(
        self,
        payload: dict,
        query_features: dict,
    ) -> tuple[float, list[str], list[str]]:
        """Score product and application overlap between query and document."""
        doc_products = [p.lower() for p in payload.get("product", [])]
        doc_apps     = [a.lower() for a in payload.get("application", [])]

        q_products = [p.lower() for p in query_features.get("product", [])]
        q_apps     = [a.lower() for a in query_features.get("application", [])]
        q_materials= [m.lower() for m in query_features.get("material", [])]

        matched_p = [p for p in q_products if any(p in dp or dp in p for dp in doc_products)]
        matched_a = [a for a in q_apps if any(a in da or da in a for da in doc_apps)]

        # Material match (partial credit)
        doc_materials = [m.lower() for m in payload.get("material", [])]
        matched_m = [m for m in q_materials if any(m in dm or dm in m for dm in doc_materials)]

        total_q = max(len(q_products) + len(q_apps) + len(q_materials), 1)
        total_matched = len(matched_p) + len(matched_a) + len(matched_m) * 0.5
        score = min(total_matched / total_q, 1.0)

        return score, matched_p, matched_a

    def _score_technical(
        self,
        payload: dict,
        query_features: dict,
    ) -> tuple[float, list[str]]:
        """Score technical parameter name overlap."""
        q_props = [p.lower() for p in query_features.get("property", [])]
        if not q_props:
            return 0.0, []

        doc_params = payload.get("technical_params", [])
        doc_param_names = [
            str(p.get("name", "")).lower()
            for p in doc_params
            if isinstance(p, dict)
        ]

        matched = [q for q in q_props if any(q in pn or pn in q for pn in doc_param_names)]
        score = len(matched) / max(len(q_props), 1)
        return min(score, 1.0), matched

    def _score_metadata(self, payload: dict, query: str) -> float:
        """Score metadata match (exact IS number match in query)."""
        # Check if the query contains the exact standard number
        std = payload.get("standard_number", "")
        if not std:
            return 0.0
        # Clean the number for regex
        std_clean = re.escape(std.strip())
        if re.search(std_clean, query, re.IGNORECASE):
            return 1.0
        # Partial match (e.g. "IS 456" in query matches "IS 456:2000")
        nums = re.findall(r"\d+", std)
        for num in nums:
            if re.search(r"\bIS\s*" + re.escape(num) + r"\b", query, re.IGNORECASE):
                return 0.8
        return 0.0
