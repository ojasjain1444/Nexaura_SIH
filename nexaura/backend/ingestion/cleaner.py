"""
cleaner.py — Phase 8: Data Cleaning

Project: Nexaura (SIH 2026 — SIH26107)

Cleans OCR artifacts and PDF extraction noise from clause text.

CRITICAL RULES:
    NEVER modify:
        - Technical values and numbers
        - Units (μm, mm, MPa, °C, kg/m², %)
        - Clause numbers
        - Standard numbers
        - Edition and year information
        - Requirement wording (shall, must, etc.)

    ALWAYS preserve:
        - raw_text (original extraction)
        - clean_text (cleaned version)

    If cleaning result is uncertain:
        - Set needs_review = True
        - Do NOT modify the original
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Optional

logger = logging.getLogger(__name__)

# Regex for technical values we must NEVER modify
TECHNICAL_VALUE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*"
    r"(?:μm|µm|mm|cm|m|km|MPa|GPa|kPa|Pa|kg|g|°C|°F|K|N|%|‰|ml|L|rpm|Hz|"
    r"g/cm[³]?|kg/m[³2]?|g/m[²2]?|N/mm[²2]?|kN)"
)

# Patterns to clean
HEADER_FOOTER_RE = re.compile(
    r"(?:Bureau of Indian Standards|BIS|www\.bis\.gov\.in|"
    r"This is a free preview|Manak Bhavan|New Delhi|"
    r"©\s*\d{4}|All rights reserved)",
    re.IGNORECASE,
)

REPEATED_PAGE_NUMBER_RE = re.compile(r"^\s*\d+\s*$", re.MULTILINE)

OCR_ARTIFACT_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"  # Control characters
    r"|(?<=[a-z])-\s+(?=[a-z])"            # Broken hyphenation: "coat-\ning"
)

BROKEN_WHITESPACE_RE = re.compile(r"[ \t]{3,}")  # 3+ spaces → single space

DUPLICATE_LINE_RE = re.compile(r"^(.+\n)\1+", re.MULTILINE)


class DataCleaner:
    """
    Cleans extracted clause text while preserving all technical content.

    Processing order:
    1. Unicode normalization
    2. Control character removal
    3. Header/footer removal
    4. Repeated page number removal
    5. Broken hyphenation repair
    6. Duplicate line removal
    7. Whitespace normalization

    Every modification is tracked. If any step fails,
    the raw_text is returned unchanged and needs_review is set.
    """

    def __init__(self, aggressive: bool = False) -> None:
        """
        Args:
            aggressive: If True, apply more aggressive cleaning.
                        Use with caution — can alter technical text.
        """
        self.aggressive = aggressive

    def clean(self, raw_text: str) -> tuple[str, bool]:
        """
        Clean extracted text.

        Args:
            raw_text: Original extracted text.

        Returns:
            Tuple of (clean_text, needs_review).
            needs_review is True if cleaning was uncertain.
        """
        if not raw_text or not raw_text.strip():
            return raw_text or "", False

        try:
            text = raw_text

            # Step 1: Unicode normalization (NFC — preserve characters)
            text = unicodedata.normalize("NFC", text)

            # Step 2: Remove control characters (but preserve tab and newline)
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)

            # Step 3: Fix encoding issues (mojibake patterns)
            text = self._fix_encoding(text)

            # Step 4: Repair broken hyphenation from PDF line wrapping
            # "coat-\ning" → "coating"
            text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

            # Step 5: Remove headers and footers
            text = self._remove_headers_footers(text)

            # Step 6: Remove standalone page numbers (line = single number)
            text = REPEATED_PAGE_NUMBER_RE.sub("", text)

            # Step 7: Remove duplicate adjacent lines
            text = DUPLICATE_LINE_RE.sub(r"\1", text)

            # Step 8: Normalize whitespace (but NOT inside technical values)
            text = self._normalize_whitespace(text)

            # Final check: ensure technical values were not modified
            needs_review = self._check_technical_integrity(raw_text, text)

            return text.strip(), needs_review

        except Exception as exc:
            logger.error("Cleaning failed: %s — returning raw text", exc)
            return raw_text, True

    def clean_knowledge_unit(self, ku) -> None:
        """
        Clean a KnowledgeUnit in place.

        Sets clean_text and text from raw_text.
        Sets needs_review if cleaning was uncertain.
        """
        if not ku.raw_text:
            ku.clean_text = ""
            return

        clean, review = self.clean(ku.raw_text)
        ku.clean_text = clean
        ku.text = clean

        if review:
            ku.needs_review = True
            if not ku.review_reason:
                ku.review_reason = "cleaning_uncertainty"

        # Update search text after cleaning
        ku.search_text = ku.build_search_text()

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _fix_encoding(self, text: str) -> str:
        """Fix common OCR encoding issues."""
        replacements = {
            "\u201c": '"',  # Left double quote
            "\u201d": '"',  # Right double quote
            "\u2018": "'",  # Left single quote
            "\u2019": "'",  # Right single quote
            "\u2013": "-",  # En dash
            "\u2014": "-",  # Em dash
            "\u2026": "...",# Ellipsis
            "\u00a0": " ",  # Non-breaking space
            "\u200b": "",   # Zero-width space
            "\u200c": "",   # Zero-width non-joiner
            "\u200d": "",   # Zero-width joiner
            "\ufeff": "",   # BOM
            # Common OCR substitutions
            r"l\/": "1/",   # l confused with 1 (raw string avoids escape warning)
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return text

    def _remove_headers_footers(self, text: str) -> str:
        """Remove BIS document headers and footers."""
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip pure header/footer lines
            if HEADER_FOOTER_RE.match(stripped):
                logger.debug("Removed header/footer line: %s", stripped[:60])
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    def _normalize_whitespace(self, text: str) -> str:
        """
        Normalize whitespace while preserving paragraph structure.
        Does NOT collapse newlines (preserves clause structure).
        """
        # Collapse multiple spaces on same line to single space
        lines = text.split("\n")
        lines = [re.sub(r"[ \t]+", " ", line) for line in lines]
        # Collapse 3+ consecutive blank lines to 2
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def _check_technical_integrity(self, original: str, cleaned: str) -> bool:
        """
        Check that technical values were not modified during cleaning.

        Returns True (needs_review) if any technical value from the original
        is missing from the cleaned text.
        """
        original_values = set(TECHNICAL_VALUE_RE.findall(original))
        cleaned_values  = set(TECHNICAL_VALUE_RE.findall(cleaned))

        missing = original_values - cleaned_values
        if missing:
            logger.warning(
                "Technical values possibly modified: %s", missing
            )
            return True
        return False
