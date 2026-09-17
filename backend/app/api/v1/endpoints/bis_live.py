"""
backend/app/api/v1/endpoints/bis_live.py — Live BIS official portal proxy endpoint.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Query

from bis_ingestion.clients.bis_standards import search_standards_api

router = APIRouter()


@router.get("/live-search")
async def live_bis_search(
    q: str = Query(..., min_length=2, description="Search term to query on official BIS portal"),
) -> dict[str, Any]:
    """
    Directly query official Bureau of Indian Standards review-service in real time.
    Provides instant live results directly from official government servers.
    """
    results = search_standards_api(q)
    return {
        "query": q,
        "total_results": len(results),
        "source": "https://standards.bis.gov.in/website/know-your-standards",
        "results": results,
    }
