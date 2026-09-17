"""
backend/app/config.py — Configuration settings for the Nexaura Backend API.
"""

from __future__ import annotations

import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = BASE_DIR.parent
DATA_DIR = WORKSPACE_DIR / "bis_ingestion" / "data"
PDF_DIR = DATA_DIR / "pdfs"

# Server Settings
API_TITLE = "Nexaura BIS Standards API"
API_VERSION = "1.0.0"
API_DESCRIPTION = (
    "Comprehensive REST API and AI Assistant for Indian Standards (BIS), "
    "accredited testing laboratories, and technical documentation."
)
API_V1_PREFIX = "/api/v1"

HOST = os.getenv("API_HOST", "0.0.0.0")
PORT = int(os.getenv("API_PORT", "8000"))

# MongoDB Settings
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "nexaura")

# CORS Origins
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
    "*",
]
