"""
chatbot_api.py — Full Chatbot Query API

Project: Nexaura (SIH 2026 — SIH26107)

This implements the RAG completion endpoints that the chatbot frontend calls.
"""

import logging
import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import google.generativeai as genai
from nexaura.backend.search.similarity import SimilarityEngine
from nexaura.backend.retrieval.applicability_filter import ApplicabilityFilter
from nexaura.backend.retrieval.answer_assembler import AnswerAssembler

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chatbot"])

class ChatRequest(BaseModel):
    query: str
    top_k: int = 5
    active_only: bool = True

class ChatResponse(BaseModel):
    answer: str
    sources: list

def get_similarity_engine():
    # Dependency placeholder - in a real app this would be initialized globally
    raise NotImplementedError("Dependency injection for SimilarityEngine needed")

@router.post("/ask", response_model=ChatResponse)
async def ask_question(request: ChatRequest):
    """Answers a question using the Nexaura RAG pipeline."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
         raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")
         
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"))
    
    # 1. Retrieve
    # engine = get_similarity_engine()
    # results = engine.search(request.query, top_k=request.top_k)
    results = [] # Placeholder
    
    # 2. Filter
    filterer = ApplicabilityFilter()
    filtered_results = filterer.filter_results(results, active_only=request.active_only)
    
    # 3. Assemble
    assembler = AnswerAssembler()
    prompt = assembler.build_rag_prompt(request.query, filtered_results)
    
    # 4. Generate
    try:
        response = model.generate_content(prompt)
        answer_text = response.text
    except Exception as exc:
        logger.error("LLM Generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate answer")
        
    # Format sources for response
    sources = [{"id": r.knowledge_unit_id, "citation": assembler.citation_engine.format_citation(r)} for r in filtered_results]
        
    return ChatResponse(answer=answer_text, sources=sources)
