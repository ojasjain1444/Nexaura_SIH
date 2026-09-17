"""
config.py — Central configuration for the BIS Standards Ingestion Pipeline.

Project: Nexaura (SIH 2026 — Problem Statement SIH26107)
Source:  Official BIS websites only (bis.gov.in, standards.bis.gov.in, lims.bis.gov.in)

IMPORTANT: This pipeline only collects publicly accessible metadata.
- It respects robots.txt (Allow: / for standards.bis.gov.in).
- It does NOT bypass login, CAPTCHA, paywalls, or anti-bot mechanisms.
- It does NOT download or redistribute copyrighted BIS standard PDFs.
- It uses conservative rate limiting and request delays.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Project Paths ------------------------------------------------------------

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
CHECKPOINT_DIR = BASE_DIR / "data" / "checkpoints"

for _dir in (DATA_DIR, LOGS_DIR, CHECKPOINT_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# --- Official BIS Source URLs -------------------------------------------------
# Only official BIS government domains -- never third-party sites.

SOURCES = {
    "standards_portal": {
        "base_url": "https://standards.bis.gov.in",
        "search_url": "https://standards.bis.gov.in/website/know-your-standards",
        "published_standards_url": "https://standards.bis.gov.in/website/published-standards/published-standards-list",
        "new_standards_url": "https://standards.bis.gov.in/website/new-standards",
        "revised_standards_url": "https://standards.bis.gov.in/website/revised-standards",
        "api_base_url": "https://standardsadmin.bis.gov.in/review-service",
        "requires_js": False,
        "robots_txt": "https://standards.bis.gov.in/robots.txt",
        "allowed": True,  # robots.txt: Allow: /
    },
    "lims": {
        "base_url": "https://lims.bis.gov.in",
        # Publicly accessible search -- no login required for the search_is_number endpoint.
        "lab_search_url": "https://lims.bis.gov.in/home/search_is_number/",
        # Django HTML app -- server-side rendered tables, directly scrapeable.
        "requires_js": False,
        "robots_txt": "https://lims.bis.gov.in/robots.txt",
        # LIMS robots.txt returns 404 HTML page, meaning no restrictions declared.
        "allowed": True,
    },
    "bis_main": {
        "base_url": "https://www.bis.gov.in",
        "know_your_standard": "https://www.bis.gov.in/know-your-standard/?lang=en",
        "requires_js": False,
        "allowed": True,
    },
}

# --- HTTP Client Settings -----------------------------------------------------

# Conservative request delay range (seconds) -- respects server load.
REQUEST_DELAY_MIN = 1.0   # seconds between requests (minimum)
REQUEST_DELAY_MAX = 2.5   # seconds between requests (maximum)

REQUEST_TIMEOUT = 30       # HTTP request timeout in seconds
MAX_RETRIES = 3            # Max retries on transient failures
RETRY_BACKOFF_BASE = 2.0   # Exponential backoff base (2^attempt seconds)
MAX_RETRY_BACKOFF = 60.0   # Maximum backoff cap in seconds

# Conservative page size for LIMS scraper (their server is Django)
LIMS_PAGE_SIZE = 50        # results per page when paginating LIMS

# Standards portal concurrent requests (keep low to be respectful)
MAX_CONCURRENT_REQUESTS = 1  # Sequential only -- conservative crawl

USER_AGENT = (
    "NexauraBot/1.0 (SIH2026 Academic Research; "
    "Contact: nexaura@bis-research.ac.in; "
    "Robots-Compliant; Non-commercial)"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "DNT": "1",
}

# --- Database Settings --------------------------------------------------------

# MongoDB (primary NoSQL document database)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "nexaura")

# SQLite (local fallback / file-based)
SQLITE_DB_PATH = DATA_DIR / "bis_standards.db"

# PostgreSQL (optional -- set via environment variables)
POSTGRES_CONFIG = {
    "host": os.getenv("BIS_PG_HOST", "localhost"),
    "port": int(os.getenv("BIS_PG_PORT", "5432")),
    "database": os.getenv("BIS_PG_DB", "nexaura_bis"),
    "user": os.getenv("BIS_PG_USER", "postgres"),
    "password": os.getenv("BIS_PG_PASSWORD", ""),
}

# --- Export Settings ----------------------------------------------------------

EXPORT_CSV_PATH = DATA_DIR / "bis_standards.csv"
EXPORT_JSON_PATH = DATA_DIR / "bis_standards.json"
EXPORT_JSONL_PATH = DATA_DIR / "bis_standards.jsonl"

# RAG chunk output
RAG_CHUNKS_JSONL_PATH = DATA_DIR / "rag_chunks.jsonl"

# --- Checkpoint / Incremental Update Settings ---------------------------------

CHECKPOINT_FILE = CHECKPOINT_DIR / "crawl_state.json"
# Records already seen are tracked by (standard_number, source) to avoid re-crawl.
DEDUP_DB_PATH = CHECKPOINT_DIR / "seen_ids.db"

# --- Crawl Scope --------------------------------------------------------------

# For the initial test crawl -- limit to first N records.
TEST_CRAWL_LIMIT = 50

# IS number range to crawl (for LIMS sequential scan).
# IS standards are numbered from 1 to ~20000+
LIMS_IS_START = 1
LIMS_IS_END = 500        # adjust for full crawl

# --- RAG Chunking Settings ----------------------------------------------------

RAG_CHUNK_SIZE = 512        # max tokens per chunk (approximate)
RAG_CHUNK_OVERLAP = 64      # overlap between consecutive chunks (tokens)

# --- Logging ------------------------------------------------------------------

LOG_LEVEL = "INFO"
LOG_FILE = LOGS_DIR / "ingestion.log"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
