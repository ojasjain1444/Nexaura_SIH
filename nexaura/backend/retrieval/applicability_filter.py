"""
applicability_filter.py — Applicability Filtering

Project: Nexaura (SIH 2026 — SIH26107)

Filters retrieval results based on status (e.g. In Force vs Withdrawn)
and applicability logic before passing to the generator.
"""

from __future__ import annotations
import logging
from nexaura.backend.search.similarity import SimilarityResult

logger = logging.getLogger(__name__)

class ApplicabilityFilter:
    """Filters results based on status and metadata."""

    def filter_active_only(self, results: list[SimilarityResult]) -> list[SimilarityResult]:
        """Keep only 'In Force' or 'Reaffirmed' standards."""
        filtered = []
        for r in results:
            status = r.payload.get("status", "unknown").lower()
            if status in ("in force", "reaffirmed", "unknown"): # Keep unknown just in case
                filtered.append(r)
            else:
                logger.debug("Filtered out %s (status: %s)", r.standard_number, status)
        return filtered

    def filter_results(self, results: list[SimilarityResult], active_only: bool = True) -> list[SimilarityResult]:
        if active_only:
            return self.filter_active_only(results)
        return results
