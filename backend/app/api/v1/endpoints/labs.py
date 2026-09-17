"""
backend/app/api/v1/endpoints/labs.py — Accredited testing laboratories discovery endpoints.
"""

from __future__ import annotations

import math
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.app.core.db import get_adb
from backend.app.models.schemas import LabResponse, PaginatedResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse[LabResponse])
async def list_labs(
    q: Optional[str] = Query(None, description="Search by lab name or address"),
    state: Optional[str] = Query(None, description="Filter by Indian State (e.g. 'Gujarat', 'Maharashtra')"),
    district: Optional[str] = Query(None, description="Filter by District"),
    is_number: Optional[str] = Query(None, description="Filter by IS Standard Number (e.g. 'IS 456', 'IS 1')"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    adb: AsyncIOMotorDatabase = Depends(get_adb),
):
    """Search and filter official BIS accredited testing laboratories."""
    filters: dict = {}

    if state:
        filters["state"] = {"$regex": f"^{re.escape(state)}", "$options": "i"}

    if district:
        filters["district"] = {"$regex": f"^{re.escape(district)}", "$options": "i"}

    if is_number:
        clean = is_number.strip()
        filters["is_number"] = {"$regex": re.escape(clean), "$options": "i"}

    if q:
        query_str = q.strip()
        filters["$or"] = [
            {"lab_name": {"$regex": re.escape(query_str), "$options": "i"}},
            {"product": {"$regex": re.escape(query_str), "$options": "i"}},
            {"remark": {"$regex": re.escape(query_str), "$options": "i"}},
        ]

    total = await adb["labs"].count_documents(filters)
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    skip = (page - 1) * page_size

    cursor = adb["labs"].find(filters, {"_id": 0}).skip(skip).limit(page_size)
    items = await cursor.to_list(length=page_size)

    return PaginatedResponse[LabResponse](
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )
