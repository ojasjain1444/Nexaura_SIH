"""
backend/app/api/v1/api_router.py — Aggregates all v1 API route modules.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.v1.endpoints import (
    bis_live,
    labs,
    rag,
    standards,
    stats,
)

api_router = APIRouter()

api_router.include_router(standards.router, prefix="/standards", tags=["Standards"])
api_router.include_router(labs.router, prefix="/labs", tags=["Testing Laboratories"])
api_router.include_router(rag.router, prefix="/rag", tags=["AI & RAG Assistant"])
api_router.include_router(bis_live.router, prefix="/bis", tags=["Live BIS Proxy"])
api_router.include_router(stats.router, prefix="/stats", tags=["System & Statistics"])
