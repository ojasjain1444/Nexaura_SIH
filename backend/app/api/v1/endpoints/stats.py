"""
backend/app/api/v1/endpoints/stats.py — Database statistics and system health overview.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.app.config import MONGO_DB_NAME
from backend.app.core.db import get_adb
from backend.app.models.schemas import StatsResponse

router = APIRouter()


@router.get("", response_model=StatsResponse)
async def get_system_stats(
    adb: AsyncIOMotorDatabase = Depends(get_adb),
):
    """Return high-level database metrics, collection counts, and system status."""
    standards_count = await adb["standards"].count_documents({})
    labs_count = await adb["labs"].count_documents({})
    rag_chunks_count = await adb["rag_chunks"].count_documents({})
    pdf_documents_count = await adb["documents"].count_documents({})
    gridfs_files_count = await adb["fs.files"].count_documents({})

    return StatsResponse(
        standards_count=standards_count,
        labs_count=labs_count,
        rag_chunks_count=rag_chunks_count,
        pdf_documents_count=pdf_documents_count,
        gridfs_files_count=gridfs_files_count,
        database_name=MONGO_DB_NAME,
        status="healthy",
    )
