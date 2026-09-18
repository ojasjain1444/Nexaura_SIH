"""
POST /api/rag/retrieve — semantic retrieval only.

This is NOT a RAG answer endpoint. It returns evidence chunks with
similarity scores; it never calls an LLM and never generates prose. See
app/rag/retrieval.py's module docstring for the architectural boundary
this enforces.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rag.retrieval import RetrievalError, RetrievalService
from app.schemas.retrieval import RetrievalRequest, RetrievalResponse

router = APIRouter(tags=["rag"])


@router.post("/rag/retrieve", response_model=RetrievalResponse)
def retrieve(payload: RetrievalRequest, db: Session = Depends(get_db)) -> RetrievalResponse:
    service = RetrievalService(db)
    try:
        results = service.retrieve(query=payload.query, top_k=payload.top_k, document_id=payload.document_id)
    except RetrievalError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return RetrievalResponse(results=results)
