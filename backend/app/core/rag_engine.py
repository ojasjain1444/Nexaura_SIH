"""
backend/app/core/rag_engine.py — High-precision RAG retrieval and citation engine for BIS standards.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


class RAGEngine:
    """Retrieves relevant standards clauses and formats evidence-based answers."""

    async def search_chunks(
        self,
        adb: AsyncIOMotorDatabase,
        query: str,
        top_k: int = 5,
        standard_number: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Search and rank chunks from MongoDB using hybrid text search + RapidFuzz."""
        filters: dict[str, Any] = {}
        if standard_number:
            clean_std = standard_number.strip().upper()
            filters["standard_number"] = {"$regex": re.escape(clean_std), "$options": "i"}

        candidates: list[dict[str, Any]] = []

        # 1. Text Search (if index available)
        try:
            text_query = dict(filters)
            text_query["$text"] = {"$search": query}
            cursor = adb["rag_chunks"].find(
                text_query,
                {"score": {"$meta": "textScore"}, "_id": 0},
            ).sort([("score", {"$meta": "textScore"})]).limit(top_k * 3)
            candidates = await cursor.to_list(length=top_k * 3)
        except Exception:
            candidates = []

        # 2. Fallback or augment with regex search across words
        if len(candidates) < top_k:
            words = [w for w in re.split(r"\W+", query) if len(w) > 2]
            if words:
                regex_pattern = "|".join(re.escape(w) for w in words[:4])
                regex_filter = dict(filters)
                regex_filter["text"] = {"$regex": regex_pattern, "$options": "i"}
                cursor = adb["rag_chunks"].find(regex_filter, {"_id": 0}).limit(top_k * 3)
                regex_results = await cursor.to_list(length=top_k * 3)

                existing_ids = {c.get("chunk_id") for c in candidates}
                for r in regex_results:
                    if r.get("chunk_id") not in existing_ids:
                        candidates.append(r)

        # 3. Fuzzy Re-ranking using RapidFuzz
        q_lower = query.lower()
        scored_chunks = []
        for chunk in candidates:
            text = chunk.get("text", "")
            std_num = chunk.get("standard_number", "")

            # Score similarity with text and standard number
            text_score = fuzz.partial_ratio(q_lower, text.lower())
            std_boost = 30 if q_lower in std_num.lower() else 0
            total_score = min(100.0, text_score + std_boost)

            chunk["score"] = round(total_score, 2)
            scored_chunks.append(chunk)

        # Sort by highest score
        scored_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
        return scored_chunks[:top_k]

    def synthesize_answer(self, query: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        """Generate structured answer with citations based on retrieved context."""
        if not chunks:
            return {
                "answer": (
                    f"No specific clauses found in the database for '{query}'. "
                    "Try searching by standard number (e.g. 'IS 456', 'IS 1786') or broader keywords like 'concrete', 'steel', 'water'."
                ),
                "cited_standards": [],
                "citations": [],
            }

        cited_standards = sorted(list({c.get("standard_number", "") for c in chunks if c.get("standard_number")}))
        citations = []
        for c in chunks:
            citations.append({
                "standard_number": c.get("standard_number", ""),
                "section": c.get("section", "General"),
                "source_url": c.get("source_url", ""),
                "chunk_id": c.get("chunk_id", ""),
            })

        # Build clean synthesized response
        best_chunk = chunks[0]
        snippet = best_chunk.get("text", "").strip()
        lines = [line.strip() for line in snippet.split("\n") if line.strip() and not line.startswith("[")]
        summary_text = " ".join(lines[:3]) if lines else snippet[:300]

        answer = (
            f"Based on official Indian Standards records ({', '.join(cited_standards)}):\n\n"
            f"{summary_text}\n\n"
            f"Key Reference: {best_chunk.get('standard_number')} ({best_chunk.get('section', 'General Specification')})."
        )

        return {
            "answer": answer,
            "cited_standards": cited_standards,
            "citations": citations,
        }


rag_engine = RAGEngine()
