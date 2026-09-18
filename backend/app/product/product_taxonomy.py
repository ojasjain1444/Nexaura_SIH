"""
Product category/attribute normalization — Phase 12.

Phase 10 discovered that clarification-question selection
(app/product/clarification.py's CATEGORY_QUESTIONS.get(profile.product_category, ...))
was a bare, case-sensitive exact-string dict lookup: a local LLM extracting
"household appliances", "electric water heater", or "water heating
equipment" instead of the exact seeded key "water_heater" would silently
fall through to the generic FALLBACK_QUESTIONS, never reaching the
category-specific clarification flow. Confirmed live during Phase 10/11
testing against qwen2.5:7b.

This module is the fix: a deterministic, keyword-based normalizer mapping
free-text category mentions to a small set of CONTROLLED categories. It is
intentionally NOT a machine-learning classifier or an LLM call — per
explicit design decision, normalization must be deterministic, testable,
and conservative. A category that cannot be confidently matched returns
None (the caller then treats it as NEEDS_CLARIFICATION / falls back to
generic questions) — normalization NEVER invents a new category the user
did not effectively describe, and never lets an LLM define an arbitrary
category string.

Extending the taxonomy means adding an entry to CATEGORY_SYNONYMS — no
control-flow changes required, matching CATEGORY_QUESTIONS' own
"reusable framework" design in clarification.py.
"""

import re

# Each controlled category maps to a list of phrases whose presence
# (case-insensitive substring match) confidently identifies that category.
# Ordered by specificity where it matters: a more specific synonym list is
# checked before a more generic one would be, though today's categories
# don't overlap in practice.
CATEGORY_SYNONYMS: dict[str, list[str]] = {
    "water_heater": [
        "water heater",
        "water heating",
        "geyser",
        "immersion heater",
        "hot water storage",
        "hot water system",
    ],
    "water_purifier": [
        "water purifier",
        "water purification",
        "ro purifier",
        "ro system",
        "water filter",
        "drinking water treatment",
    ],
}

# The controlled category set — anything not in this set can never be
# returned by normalize_category(), even if it happens to match a keyword,
# guarding against a future typo in CATEGORY_SYNONYMS silently introducing
# an uncontrolled category value.
CONTROLLED_CATEGORIES = frozenset(CATEGORY_SYNONYMS.keys())


def normalize_category(raw: str | None) -> str | None:
    """Maps free-text category wording to a controlled category, or None
    if no confident match exists. Case-insensitive substring matching
    against CATEGORY_SYNONYMS — deterministic and testable, never a
    fuzzy/ML match that could produce a different result for a
    near-identical input across runs.

    Idempotent: normalize_category(normalize_category(x)) always equals
    normalize_category(x). A controlled category value (e.g.
    "water_heater") is recognized directly first — the CATEGORY_SYNONYMS
    substring check alone would miss it, since synonyms use spaces
    ("water heater") while controlled keys use underscores
    ("water_heater"). Callers must be able to safely re-normalize a value
    that may already be normalized (see
    app/product/profile_extraction.py's apply_updates(), which discovered
    this exact non-idempotence as a real bug during Phase 13)."""
    if not raw or not raw.strip():
        return None
    lowered = raw.strip().lower()
    if lowered in CONTROLLED_CATEGORIES:
        return lowered
    for category, synonyms in CATEGORY_SYNONYMS.items():
        if any(synonym in lowered for synonym in synonyms):
            return category
    return None


# --- Attribute normalization ---
#
# Deliberately limited to the two attributes that actually affect
# clarification/applicability logic today (see clarification.py's
# CATEGORY_QUESTIONS asking about intended_use and product_type for
# water_heater) — not a general unit-parsing system. Adding
# voltage/power/capacity normalization would be speculative: nothing
# downstream currently consumes those as structured values.

_DOMESTIC_PATTERN = re.compile(r"\b(domestic|household|home|residential)\b", re.IGNORECASE)
_COMMERCIAL_PATTERN = re.compile(r"\b(commercial|industrial|business)\b", re.IGNORECASE)


def normalize_intended_use(raw: str | None) -> str | None:
    """Returns "domestic", "commercial", or None (left as-is / unknown) —
    never guesses when neither pattern matches."""
    if not raw:
        return None
    if _DOMESTIC_PATTERN.search(raw):
        return "domestic"
    if _COMMERCIAL_PATTERN.search(raw):
        return "commercial"
    return None


_STORAGE_PATTERN = re.compile(r"\b(storage|storage-type|tank)\b", re.IGNORECASE)
_INSTANT_PATTERN = re.compile(r"\b(instant|instantaneous|tankless|on-demand|on demand)\b", re.IGNORECASE)


def normalize_water_heater_type(raw: str | None) -> str | None:
    """Water-heater-specific product_type normalization: "storage" or
    "instant", or None if neither pattern matches. Kept separate from a
    general product_type normalizer since "storage vs instant" is a
    water-heater-specific distinction, not a universal one."""
    if not raw:
        return None
    if _STORAGE_PATTERN.search(raw):
        return "storage"
    if _INSTANT_PATTERN.search(raw):
        return "instant"
    return None
