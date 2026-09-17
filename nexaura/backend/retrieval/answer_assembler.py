"""
answer_assembler.py — RAG Prompt Assembly

Project: Nexaura (SIH 2026 — SIH26107)

Assembles the final prompt for the generative LLM using the 
retrieved and filtered sources.
"""

from __future__ import annotations
from nexaura.backend.retrieval.citation_engine import CitationEngine
from nexaura.backend.search.similarity import SimilarityResult

class AnswerAssembler:
    """Constructs prompts for the generation phase."""

    def __init__(self):
        self.citation_engine = CitationEngine()

    def build_rag_prompt(self, query: str, sources: list[SimilarityResult]) -> str:
        sources_text = self.citation_engine.format_sources_block(sources)
        
        prompt = f"""You are Nexaura, an AI Assistant for Indian Standards and BIS Services.
Answer the user's question based strictly on the provided SOURCES.
If the answer is not contained in the SOURCES, say "I cannot find the answer in the provided standards."
Do not invent information. Do not hallucinate technical values.
Always cite your sources using the provided citation format (e.g. [IS 456:2000, Clause 5.1]).

QUESTION: {query}

{sources_text}

ANSWER:
"""
        return prompt
