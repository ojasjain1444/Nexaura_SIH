"""parsers — Text normalisation and HTML parsing helpers."""

from .text_utils import (
    clean_text,
    extract_amendment_numbers,
    extract_ics_codes,
    extract_is_numbers,
    extract_year,
    normalise_date,
    normalise_is_number,
    normalise_status,
    parse_is_components,
    slugify,
    strip_html_tags,
)

__all__ = [
    "clean_text",
    "extract_amendment_numbers",
    "extract_ics_codes",
    "extract_is_numbers",
    "extract_year",
    "normalise_date",
    "normalise_is_number",
    "normalise_status",
    "parse_is_components",
    "slugify",
    "strip_html_tags",
]
