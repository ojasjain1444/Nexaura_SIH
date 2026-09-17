"""
bis_id_normalizer.py — BIS Standard Number Normalization

Project: Nexaura (SIH 2026 — SIH26107)

Normalizes IS standard number formats consistently.

Input variations handled:
    "IS456"        → "IS 456"
    "IS 456:2000"  → "IS 456"
    "I.S. 456"     → "IS 456"
    "IS456 PART1"  → "IS 456 Part 1"
    "is 456"       → "IS 456"
    "IS 15700:2005 Amd 1" → "IS 15700"

Also provides:
    - BIS PDF filename → standard number extraction
    - Standard number → search-safe slug
"""

from __future__ import annotations

import re
from typing import Optional


# Matches IS numbers in many formats
_IS_RE = re.compile(
    r"(?:I\.?S\.?)\s*"              # IS or I.S. prefix
    r"(\d+)"                         # Main number
    r"(?:\s*(?:PART|Part|Pt\.?)\s*(\d+))?"  # Optional part
    r"(?:\s*(?:SEC|Sec\.?)\s*(\d+))?"       # Optional section
    r"(?:\s*:\s*(\d{4}))?"          # Optional year suffix ":2024"
    r"(?:\s+Amd\.?\s+\d+)?",        # Optional amendment (stripped)
    re.IGNORECASE,
)

# IS number slug (for IDs and filenames)
_SAFE_RE = re.compile(r"[^A-Za-z0-9]")


def normalize(raw: str) -> Optional[str]:
    """
    Normalize an IS standard number to canonical format.

    Args:
        raw: Raw standard number string.

    Returns:
        Normalized string like "IS 456", "IS 456 Part 1", or None if invalid.

    Examples:
        >>> normalize("IS456")
        'IS 456'
        >>> normalize("IS 456:2000")
        'IS 456'
        >>> normalize("IS 456 PART 2")
        'IS 456 Part 2'
        >>> normalize("i.s.456")
        'IS 456'
    """
    if not raw:
        return None
    raw_clean = raw.strip()
    m = _IS_RE.search(raw_clean)
    if not m:
        return raw_clean.upper() if raw_clean else None

    num  = m.group(1)
    part = m.group(2)
    sec  = m.group(3)

    result = f"IS {num}"
    if part:
        result += f" Part {part}"
    if sec:
        result += f" Sec {sec}"
    return result


def to_slug(standard_number: str) -> str:
    """
    Convert a standard number to a URL/filename-safe slug.

    Args:
        standard_number: Normalized standard number.

    Returns:
        Slug string (alphanumeric + underscores only, uppercase).

    Examples:
        >>> to_slug("IS 456")
        'IS456'
        >>> to_slug("IS 456 Part 1")
        'IS456_Part1'
    """
    if not standard_number:
        return "UNKNOWN"
    # Remove spaces between IS and number, keep others as underscore
    cleaned = re.sub(r"IS\s+(\d+)", r"IS\1", standard_number)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = _SAFE_RE.sub("", cleaned.replace(" ", "_"))
    return cleaned.upper()


def extract_from_filename(filename: str) -> Optional[str]:
    """
    Attempt to extract an IS standard number from a PDF filename.

    Common BIS PDF filename patterns:
        IS456.pdf       → IS 456
        IS456-2000.pdf  → IS 456
        IS_1234_2024.pdf → IS 1234
        is15700.pdf     → IS 15700

    Args:
        filename: PDF filename (basename or full path).

    Returns:
        Normalized IS number or None.
    """
    import os
    basename = os.path.splitext(os.path.basename(filename))[0]

    # Try direct IS pattern match
    result = normalize(basename)
    if result and result.startswith("IS"):
        return result

    # Try extracting digits after "IS"
    m = re.search(r"IS[\s_\-]?(\d+)", basename, re.IGNORECASE)
    if m:
        return f"IS {m.group(1)}"

    return None


def are_same_standard(a: str, b: str) -> bool:
    """
    Check if two standard number strings refer to the same standard.

    Args:
        a: First standard number string.
        b: Second standard number string.

    Returns:
        True if they normalize to the same canonical form.
    """
    na = normalize(a)
    nb = normalize(b)
    if na is None or nb is None:
        return False
    return na.upper() == nb.upper()
