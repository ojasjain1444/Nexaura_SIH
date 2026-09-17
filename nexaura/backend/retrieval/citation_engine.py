"""
citation_engine.py — Citation Formatting and Verification

Project: Nexaura (SIH 2026 — SIH26107)

Formats and validates citations from SimilarityResult objects
to ensure the chatbot always grounds its answers in real BIS clauses.
"""

from __future__ import annotations

import logging
from typing import Optional
from nexaura.backend.search.similarity import SimilarityResult

logger = logging.getLogger(__name__)

class CitationEngine:
    """Formats similarity results into standard citations."""

    def format_citation(self, result: SimilarityResult) -> str:
        """Format a single similarity result into a citation string."""
        citation = f"[{result.standard_number}"
        if result.edition:
            citation += f":{result.edition}"
        if result.clause and result.clause != "SCOPE" and result.clause != "FOREWORD":
             citation += f", Clause {result.clause}"
        elif result.clause:
             citation += f", {result.clause}"
        if result.page_start > 0:
            citation += f", pg. {result.page_start}"
        citation += "]"
        return citation

    def format_sources_block(self, results: list[SimilarityResult]) -> str:
        """Format a block of sources for the LLM prompt or final output."""
        if not results:
            return "No sources available."
        
        block = "SOURCES:\n"
        for i, r in enumerate(results):
            cit = self.format_citation(r)
            text = r.payload.get("text", "")
            # Truncate text for context if it's too long
            if len(text) > 1000:
                 text = text[:1000] + "..."
            
            block += f"{i+1}. {cit}\n"
            block += f"   Heading: {r.heading or 'N/A'}\n"
            block += f"   Content: {text}\n\n"
        return block
