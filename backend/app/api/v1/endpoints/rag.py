"""
backend/app/api/v1/endpoints/rag.py — RAG retrieval and standards question answering endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.app.core.db import get_adb
from backend.app.core.rag_engine import rag_engine
from backend.app.models.schemas import (
    RAGChunkResponse,
    RAGQueryRequest,
    RAGQueryResponse,
)

router = APIRouter()


@router.post("/query", response_model=RAGQueryResponse)
async def query_rag(
    request: RAGQueryRequest,
    adb: AsyncIOMotorDatabase = Depends(get_adb),
):
    """
    Ask a question or search for technical requirements across Indian Standards.
    Returns synthesized answer, citations, and ranked context chunks.
    """
    # 1. Retrieve top chunks from MongoDB
    chunks = await rag_engine.search_chunks(
        adb=adb,
        query=request.query,
        top_k=request.top_k,
        standard_number=request.standard_number,
    )

    # 2. Synthesize structured answer
    synth = rag_engine.synthesize_answer(request.query, chunks)

    chunk_responses = [
        RAGChunkResponse(
            chunk_id=c.get("chunk_id", ""),
            standard_number=c.get("standard_number", ""),
            text=c.get("text", ""),
            token_count=c.get("token_count", 0),
            source_url=c.get("source_url", ""),
            section=c.get("section"),
            score=c.get("score"),
        )
        for c in chunks
    ]

    return RAGQueryResponse(
        query=request.query,
        answer=synth["answer"],
        cited_standards=synth["cited_standards"],
        citations=synth["citations"],
        chunks=chunk_responses,
    )
