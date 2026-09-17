"""
parsers/text_utils.py — Shared text normalisation and extraction utilities.

These helpers are used by the source-specific scrapers to clean and
normalise raw text extracted from HTML before it goes into the schema.
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# IS number helpers
# ---------------------------------------------------------------------------

# Regex that captures the major parts of an IS number:
#   IS 1239 Part 1 Sec 2 (2022)
_IS_PATTERN = re.compile(
    r"\b(IS)\s*(\d+)"
    r"(?:\s*[Pp]art\s*(\d+))?"
    r"(?:\s*[Ss]ec(?:tion)?\s*(\d+))?"
    r"(?:\s*\((\d{4})\))?",
    re.IGNORECASE,
)


def normalise_is_number(raw: str) -> str:
    """Normalise an IS number string to canonical form: 'IS XXXX Part N Sec M'."""
    raw = raw.strip().upper()
    # Remove extra whitespace
    raw = re.sub(r"\s+", " ", raw)
    return raw


def extract_is_numbers(text: str) -> list[str]:
    """Extract all IS numbers found in a block of text."""
    results = []
    for m in _IS_PATTERN.finditer(text):
        parts = [f"IS {m.group(2)}"]
        if m.group(3):
            parts.append(f"Part {m.group(3)}")
        if m.group(4):
            parts.append(f"Sec {m.group(4)}")
        results.append(" ".join(parts).upper())
    return list(dict.fromkeys(results))  # preserve order, deduplicate


def parse_is_components(raw: str) -> dict:
    """
    Parse an IS number string into its components.

    Returns:
        dict with keys: doc_no, part, section, year  (all str or None)
    """
    m = _IS_PATTERN.match(raw.strip())
    if not m:
        return {"doc_no": None, "part": None, "section": None, "year": None}
    return {
        "doc_no": m.group(2),
        "part": m.group(3),
        "section": m.group(4),
        "year": m.group(5),
    }


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")


def extract_year(text: str) -> Optional[str]:
    """Extract the first 4-digit year from a string."""
    m = _YEAR_RE.search(text)
    return m.group(1) if m else None


def normalise_date(raw: Optional[str]) -> Optional[str]:
    """
    Try to normalise a date string to ISO format (YYYY-MM-DD).
    Falls back to the raw string if parsing fails.
    """
    if not raw:
        return None
    raw = raw.strip()
    m = _DATE_RE.search(raw)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        if len(year) == 2:
            year = f"20{year}" if int(year) <= 30 else f"19{year}"
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return raw


# ---------------------------------------------------------------------------
# Text cleaning helpers
# ---------------------------------------------------------------------------

def clean_text(text: Optional[str], max_len: int = 5000) -> Optional[str]:
    """
    Strip and collapse whitespace, optionally truncate.
    Returns None for empty or whitespace-only strings.
    """
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return text[:max_len] if max_len else text


def slugify(text: str) -> str:
    """Convert a standard number to a URL-safe slug, e.g. 'IS 456' -> 'is-456'."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def extract_amendment_numbers(text: str) -> list[str]:
    """Extract amendment numbers from text, e.g. 'AMD 1', 'Amendment 2'."""
    return re.findall(r"(?:AMD|Amendment)\s*(\d+)", text, re.IGNORECASE)


def extract_ics_codes(text: str) -> list[str]:
    """Extract ICS codes (e.g. '91.080.30') from text."""
    return re.findall(r"\b\d{2}\.\d{3}(?:\.\d{2})?\b", text)


def strip_html_tags(html: str) -> str:
    """Remove all HTML tags from a string."""
    return re.sub(r"<[^>]+>", " ", html)


# ---------------------------------------------------------------------------
# Status normalisation
# ---------------------------------------------------------------------------

_STATUS_MAP: dict[str, str] = {
    "in force": "In Force",
    "current": "In Force",
    "active": "In Force",
    "published": "In Force",
    "under revision": "Under Revision",
    "under review": "Under Revision",
    "being revised": "Under Revision",
    "revised": "Revised",
    "withdrawn": "Withdrawn",
    "cancelled": "Withdrawn",
    "superseded": "Superseded",
    "reaffirmed": "Reaffirmed",
    "reaffirmation": "Reaffirmed",
}


def normalise_status(raw: Optional[str]) -> Optional[str]:
    """Normalise a status string to a canonical value."""
    if not raw:
        return None
    key = raw.strip().lower()
    return _STATUS_MAP.get(key, raw.strip())
