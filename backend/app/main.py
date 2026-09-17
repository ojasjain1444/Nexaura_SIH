"""
backend/app/main.py — Main FastAPI Application instance for Nexaura.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from backend.app.api.v1.api_router import api_router
from backend.app.config import (
    API_DESCRIPTION,
    API_TITLE,
    API_V1_PREFIX,
    API_VERSION,
    CORS_ORIGINS,
)
from backend.app.core.db import db_manager
from backend.app.models.schemas import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("nexaura_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("Starting up Nexaura API...")
    db_manager.connect()
    # Verify DB connectivity
    try:
        count = await db_manager.adb["standards"].count_documents({})
        logger.info("Connected to MongoDB successfully! %d standards ready to serve.", count)
    except Exception as e:
        logger.error("Failed to ping MongoDB: %s", e)

    yield

    logger.info("Shutting down Nexaura API...")
    db_manager.close()


app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description=API_DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 API routes
app.include_router(api_router, prefix=API_V1_PREFIX)


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to interactive API documentation."""
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse, tags=["System & Statistics"])
async def health_check():
    """Health check endpoint confirming API and MongoDB status."""
    connected = False
    total_standards = 0
    try:
        total_standards = await db_manager.adb["standards"].count_documents({})
        connected = True
    except Exception:
        connected = False

    return HealthResponse(
        status="ok" if connected else "degraded",
        version=API_VERSION,
        database_connected=connected,
        total_standards=total_standards,
    )


if __name__ == "__main__":
    import uvicorn
    from backend.app.config import HOST, PORT

    uvicorn.run("backend.app.main:app", host=HOST, port=PORT, reload=True)
