"""
backend/app/api/v1/endpoints/standards.py — Standards search, detail, and PDF download endpoints.
"""

from __future__ import annotations

import io
import math
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.app.core.db import get_adb, get_gridfs
from backend.app.models.schemas import (
    LabResponse,
    PaginatedResponse,
    StandardDetail,
    StandardSummary,
)

router = APIRouter()


@router.get("", response_model=PaginatedResponse[StandardSummary])
async def list_standards(
    q: Optional[str] = Query(None, description="Keyword search (e.g. 'IS 456', 'solar', 'steel')"),
    status: Optional[str] = Query(None, description="Filter by status (e.g. 'IN FORCE', 'WITHDRAWN')"),
    department: Optional[str] = Query(None, description="Filter by department code"),
    has_pdf: Optional[bool] = Query(None, description="Filter standards with available PDF"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    adb: AsyncIOMotorDatabase = Depends(get_adb),
):
    """List and search official Indian Standards with pagination and filtering."""
    filters: dict = {}

    if status:
        filters["status"] = {"$regex": f"^{re.escape(status)}", "$options": "i"}

    if department:
        filters["department"] = department

    if has_pdf is not None:
        filters["has_pdf"] = has_pdf

    if q:
        query_str = q.strip()
        filters["$or"] = [
            {"standard_number": {"$regex": re.escape(query_str), "$options": "i"}},
            {"title": {"$regex": re.escape(query_str), "$options": "i"}},
            {"scope": {"$regex": re.escape(query_str), "$options": "i"}},
        ]

    total = await adb["standards"].count_documents(filters)
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    skip = (page - 1) * page_size

    cursor = adb["standards"].find(filters, {"_id": 0}).skip(skip).limit(page_size)
    items = await cursor.to_list(length=page_size)

    return PaginatedResponse[StandardSummary](
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )


@router.get("/{standard_number}", response_model=StandardDetail)
async def get_standard_detail(
    standard_number: str,
    adb: AsyncIOMotorDatabase = Depends(get_adb),
):
    """Fetch complete metadata for a single standard number."""
    clean = standard_number.strip().upper()
    doc = await adb["standards"].find_one({"standard_number": clean}, {"_id": 0})
    if not doc:
        # Fuzzy match
        doc = await adb["standards"].find_one(
            {"standard_number": {"$regex": f"^{re.escape(clean)}", "$options": "i"}},
            {"_id": 0},
        )

    if not doc:
        raise HTTPException(status_code=404, detail=f"Standard '{standard_number}' not found in database")

    # Check if PDF exists in documents collection or GridFS
    if not doc.get("has_pdf"):
        pdf_doc = await adb["documents"].find_one(
            {"standard_number": {"$regex": f"^{re.escape(clean)}", "$options": "i"}}
        )
        if pdf_doc:
            doc["has_pdf"] = True
            doc["pdf_filename"] = pdf_doc.get("filename")
            doc["gridfs_id"] = str(pdf_doc.get("gridfs_id"))
            doc["pdf_pages_indexed"] = pdf_doc.get("page_count", 0)

    return doc


@router.get("/{standard_number}/pdf")
async def download_standard_pdf(
    standard_number: str,
    adb: AsyncIOMotorDatabase = Depends(get_adb),
    fs=Depends(get_gridfs),
):
    """Stream or download official standard PDF stored inside MongoDB GridFS."""
    clean = standard_number.strip().upper()
    doc = await adb["documents"].find_one(
        {"standard_number": {"$regex": f"^{re.escape(clean)}", "$options": "i"}}
    )

    if not doc:
        # Fallback to standards collection
        std = await adb["standards"].find_one(
            {"standard_number": {"$regex": f"^{re.escape(clean)}", "$options": "i"}}
        )
        if not std or not std.get("has_pdf"):
            raise HTTPException(
                status_code=404,
                detail=f"No PDF document available in database for standard '{standard_number}'",
            )
        filename = std.get("pdf_filename", f"{clean.replace(' ', '_')}.pdf")
    else:
        filename = doc.get("filename")

    # Fetch from GridFS
    grid_file = fs.find_one({"filename": filename})
    if not grid_file:
        raise HTTPException(status_code=404, detail=f"PDF file '{filename}' not found in MongoDB GridFS")

    pdf_bytes = grid_file.read()
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@router.get("/{standard_number}/labs", response_model=list[LabResponse])
async def get_labs_for_standard(
    standard_number: str,
    adb: AsyncIOMotorDatabase = Depends(get_adb),
):
    """Fetch recognized testing laboratories accredited for this standard."""
    clean = standard_number.replace("IS", "").strip().split(":")[0].strip()
    cursor = adb["labs"].find(
        {
            "$or": [
                {"is_doc_no": clean},
                {"is_number": {"$regex": f"\\b{re.escape(clean)}\\b", "$options": "i"}},
            ]
        },
        {"_id": 0},
    )
    labs = await cursor.to_list(length=100)
    return labs
