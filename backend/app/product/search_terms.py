"""
Search-term derivation — Phase 10, extended in Phase 13.

Turns a ProductProfile's stated attributes into retrieval query terms.
Every term returned is either copied verbatim from a profile field or a
plain combination of two such fields (e.g. "{category} {type}") — no
technical vocabulary is invented that the user did not actually state.
This is what "do not invent technical terminology blindly" means in
practice: the function has no domain knowledge of BIS standards, water
heaters, or anything else — it only rearranges what's already on the
profile.

Phase 13 adds:
  - attribute terms (capacity, electrical_characteristics, materials,
    target_market, manufacturing_location) that Phase 10 never included —
    each still copied verbatim, never combined into invented phrases.
  - extract_exact_identifiers(): pulls BIS standard-number-shaped tokens
    (reusing app.ingestion.metadata_extraction.STANDARD_NUMBER_PATTERN,
    the same pattern that already recognizes real IS numbers during
    ingestion) out of raw text BEFORE it gets diluted into a general
    search-term list. An exact identifier like "IS 4001:2021" must remain
    independently searchable verbatim — see app/product/hybrid_retrieval.py
    for how this feeds a guaranteed keyword-search pass, not just one term
    among many semantic-query words.
"""

from app.ingestion.metadata_extraction import STANDARD_NUMBER_PATTERN
from app.models.product_profile import ProductProfile


def extract_exact_identifiers(text: str) -> list[str]:
    """Returns every BIS standard-number-shaped token found in `text`,
    de-duplicated, in the order first seen. Reuses the exact same pattern
    app/ingestion/metadata_extraction.py uses to recognize real IS numbers
    during ingestion — an identifier is only ever "exact" if it matches
    the same convention this project already treats as authoritative."""
    seen: list[str] = []
    for match in STANDARD_NUMBER_PATTERN.finditer(text):
        value = match.group(0).strip()
        if value not in seen:
            seen.append(value)
    return seen


def derive_search_terms(profile: ProductProfile) -> list[str]:
    """Returns an ordered, de-duplicated list of search terms derived
    purely from stated ProductProfile attributes. Returns [] if the
    profile has no usable attributes yet — callers must treat that as
    'nothing to search for', not fall back to a fabricated default term."""
    terms: list[str] = []

    def add(term: str | None) -> None:
        if term and term.strip() and term.strip() not in terms:
            terms.append(term.strip())

    add(profile.product_name)
    add(profile.product_category)
    add(profile.product_type)
    add(profile.technology)

    # Combined terms are only built from fields that are both actually
    # present — never padded with a placeholder for a missing one.
    if profile.product_category and profile.product_type:
        add(f"{profile.product_type} {profile.product_category}")
    if profile.intended_use and profile.product_category:
        add(f"{profile.intended_use} {profile.product_category}")
    if profile.technology and profile.product_category:
        add(f"{profile.technology} {profile.product_category}")

    add(profile.application)

    # Phase 13: attribute terms Phase 10 never included. Still copied
    # verbatim from stated fields only — no unit parsing, no invented
    # combination phrases.
    add(profile.capacity)
    add(profile.electrical_characteristics)
    add(profile.materials)
    add(profile.target_market)
    add(profile.manufacturing_location)

    return terms


def build_query_text(profile: ProductProfile) -> str:
    """Joins derived search terms into one string suitable for semantic
    retrieval's single-query interface (RetrievalService.retrieve expects
    one query string, not a term list)."""
    return " ".join(derive_search_terms(profile))
