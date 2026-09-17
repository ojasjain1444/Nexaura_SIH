"""
reranker.py — Configurable Weighted Rank Fusion

Project: Nexaura (SIH 2026 — SIH26107)

Applies configurable weighted scoring to combine component similarity
scores into a final ranking.

Default weights (initial engineering defaults — NOT claimed optimal):
    semantic:            0.40
    keyword:             0.20
    scope:               0.15
    product_application: 0.10
    technical:           0.10
    metadata:            0.05

All weights are configurable via config.yaml.
Support for future ELO/label-based tuning is provided via
the WeightConfig interface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from nexaura.backend.search.similarity import SimilarityResult

logger = logging.getLogger(__name__)


@dataclass
class WeightConfig:
    """Configurable weights for the similarity reranker."""
    semantic:            float = 0.40
    keyword:             float = 0.20
    scope:               float = 0.15
    product_application: float = 0.10
    technical:           float = 0.10
    metadata:            float = 0.05

    def __post_init__(self) -> None:
        total = (
            self.semantic + self.keyword + self.scope
            + self.product_application + self.technical + self.metadata
        )
        if abs(total - 1.0) > 0.01:
            logger.warning(
                "WeightConfig weights do not sum to 1.0 (sum=%.3f). "
                "Normalizing automatically.", total
            )
            self.semantic            /= total
            self.keyword             /= total
            self.scope               /= total
            self.product_application /= total
            self.technical           /= total
            self.metadata            /= total

    @classmethod
    def from_dict(cls, d: dict) -> "WeightConfig":
        """Create WeightConfig from a dictionary (e.g. from config.yaml)."""
        return cls(
            semantic=           d.get("semantic", 0.40),
            keyword=            d.get("keyword", 0.20),
            scope=              d.get("scope", 0.15),
            product_application=d.get("product_application", 0.10),
            technical=          d.get("technical", 0.10),
            metadata=           d.get("metadata", 0.05),
        )

    def to_dict(self) -> dict:
        return {
            "semantic":            self.semantic,
            "keyword":             self.keyword,
            "scope":               self.scope,
            "product_application": self.product_application,
            "technical":           self.technical,
            "metadata":            self.metadata,
        }


class Reranker:
    """
    Reranks similarity results using configurable weighted scoring.

    The reranker takes SimilarityResult objects (which already have
    per-component scores) and recomputes the final_score using the
    configured weights.

    This allows:
    - Runtime weight adjustment without rerunning retrieval
    - A/B testing of different weight configurations
    - Future label-based weight tuning
    """

    def __init__(self, weights: Optional[WeightConfig] = None) -> None:
        self.weights = weights or WeightConfig()
        logger.info("Reranker initialized with weights: %s", self.weights.to_dict())

    def rerank(
        self,
        results: list[SimilarityResult],
        top_k: Optional[int] = None,
    ) -> list[SimilarityResult]:
        """
        Rerank a list of SimilarityResults using configured weights.

        Args:
            results: List of SimilarityResult objects with component scores.
            top_k: Return only top K results after reranking.

        Returns:
            Reranked list of SimilarityResult objects.
        """
        w = self.weights
        reranked = []

        for result in results:
            final = (
                w.semantic            * result.semantic_score
                + w.keyword           * result.keyword_score
                + w.scope             * result.scope_score
                + w.product_application * result.product_score
                + w.technical         * result.technical_score
                + w.metadata          * result.metadata_score
            )
            result.final_score = min(max(final, 0.0), 1.0)
            reranked.append(result)

        reranked.sort(key=lambda r: r.final_score, reverse=True)

        if top_k:
            reranked = reranked[:top_k]

        return reranked

    def update_weights(self, new_weights: dict) -> None:
        """Update weights at runtime (for tuning)."""
        self.weights = WeightConfig.from_dict(new_weights)
        logger.info("Reranker weights updated: %s", self.weights.to_dict())
