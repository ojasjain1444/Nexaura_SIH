"""
Scope and requirement extraction (Step 5b) — builds the per-standard
"feature database" (StandardScope, StandardRequirement) from a document's
already-extracted pages.

Rule-based only, same convention as the rest of ingestion: no LLM, no
probabilistic judgment. Two things are extracted, each reusing an existing,
already-tested pattern from elsewhere in this codebase rather than
inventing a new one:

  - Scope: the text of the standard's own "1 SCOPE" clause (detected with
    feature_extraction.py's SECTION_HEADING_PATTERN — the same pattern
    already used for chunk section-tagging, so this can never disagree
    with what a chunk's `section` field says). Confirmed present, in this
    exact form, across every real BIS PDF tested so far (IS 10500, IS 2062,
    IS 1786, IS 456) — always the first numbered clause, always literally
    the word "SCOPE".

  - Requirements: clauses containing an explicit obligation word
    (app.product.requirement_extraction.OBLIGATION_WORD_PATTERN) whose text
    matches one of app.product.requirement_extraction.CATEGORY_KEYWORDS —
    the exact same detection requirement_extraction.py already applied at
    query time to retrieved evidence chunks, now precomputed once per
    document over the whole document rather than per-query over whatever
    retrieval happened to surface. This is what makes the
    StandardRequirement table an ingestion-time cache of exactly the same
    logic requirement_extraction.py uses, not a second, independently
    drifting implementation of it — see that module for how these rows are
    read back and turned into a candidate's checklist items.

Scope is looked for in the first several pages only (mirroring
extract_metadata's own front-matter-skipping window in
app/ingestion/metadata_extraction.py — the real cover page, and the "1
SCOPE" clause that follows it, are reliably near the front of the document,
not scattered throughout it). Requirements are detected across all pages:
unlike scope, obligation clauses appear throughout a standard's body.
"""

import re
from dataclasses import dataclass

from app.ingestion.feature_extraction import SECTION_HEADING_PATTERN
from app.ingestion.metadata_extraction import STANDARD_NUMBER_PATTERN
from app.product.requirement_extraction import CATEGORY_KEYWORDS, OBLIGATION_WORD_PATTERN

# How many leading pages to search for the SCOPE clause — matches
# metadata_extraction's own front-matter window (see pipeline.py).
SCOPE_SEARCH_PAGE_WINDOW = 6

# The clause number and the word "SCOPE" are usually on the same line
# ("1 SCOPE"). Real BIS PDFs' native text extraction sometimes instead
# leaves "SCOPE" on its own line, with a (possibly garbled) clause-number
# line just before it (confirmed on IS 456 — a native-extraction character/
# layout quirk, not an OCR issue: the number line came through as "J"
# instead of "1"). A standalone "SCOPE" line is therefore matched on its
# own — the preceding clause-number line, whatever it contains, isn't part
# of what this needs to find.
_SCOPE_HEADING_PATTERN = re.compile(r"^\d+(?:\.\d+)*[ \t]+SCOPE[ \t]*$|^SCOPE[ \t]*$", re.MULTILINE | re.IGNORECASE)


@dataclass
class ExtractedScope:
    scope_text: str
    page_number: int


@dataclass
class ExtractedRequirement:
    category: str
    clause_number: str | None
    requirement_text: str
    page_number: int
    referenced_standards: list[str]


def extract_scope(pages: list[tuple[int, str]]) -> ExtractedScope | None:
    """`pages` is a list of (page_number, page_text) for the leading pages
    of a document (see SCOPE_SEARCH_PAGE_WINDOW). Returns the first
    "N SCOPE" clause's text found, or None if no such clause is present in
    the searched window — never guesses from unrelated text."""
    for page_number, page_text in pages:
        match = _SCOPE_HEADING_PATTERN.search(page_text)
        if not match:
            continue
        # The clause runs from its heading to the next numbered heading (or
        # end of page) — same boundary logic as
        # app/rag/chunking.py's _split_into_sections, applied here directly
        # against the heading pattern rather than importing chunking's
        # page-chunking machinery (this only needs one clause's boundary,
        # not a full re-chunk).
        next_heading = SECTION_HEADING_PATTERN.search(page_text, pos=match.end())
        end = next_heading.start() if next_heading else len(page_text)
        scope_text = page_text[match.start() : end].strip()
        if scope_text:
            return ExtractedScope(scope_text=scope_text, page_number=page_number)
    return None


def _categories_for_text(text: str) -> list[str]:
    lowered = text.lower()
    return [category.value for category, keywords in CATEGORY_KEYWORDS.items() if any(kw in lowered for kw in keywords)]


def _referenced_standards(text: str, own_standard_number: str | None) -> list[str]:
    seen: list[str] = []
    for match in STANDARD_NUMBER_PATTERN.finditer(text):
        value = match.group(0).strip()
        if value == own_standard_number or value in seen:
            continue
        seen.append(value)
    return seen


def extract_requirements(
    pages: list[tuple[int, str]], own_standard_number: str | None = None
) -> list[ExtractedRequirement]:
    """`pages` is every page's (page_number, page_text) for the whole
    document. Splits each page into its heading-delimited clauses (reusing
    SECTION_HEADING_PATTERN, the same boundary app/rag/chunking.py already
    uses for chunk section-tagging) and keeps only clauses that state an
    obligation and match a known requirement category — identical
    detection to app.product.requirement_extraction, just run once here
    over the whole document instead of per-query over retrieved evidence."""
    requirements: list[ExtractedRequirement] = []
    for page_number, page_text in pages:
        for clause_number, clause_text in _split_into_clauses(page_text):
            if not OBLIGATION_WORD_PATTERN.search(clause_text):
                continue
            categories = _categories_for_text(clause_text)
            if not categories:
                continue
            referenced = _referenced_standards(clause_text, own_standard_number)
            for category in categories:
                requirements.append(
                    ExtractedRequirement(
                        category=category,
                        clause_number=clause_number,
                        requirement_text=clause_text,
                        page_number=page_number,
                        referenced_standards=referenced,
                    )
                )
    return requirements


def _split_into_clauses(page_text: str) -> list[tuple[str | None, str]]:
    """Same heading-boundary logic as app/rag/chunking.py's
    _split_into_sections, duplicated in miniature here rather than imported
    directly: that function returns whole (possibly multi-clause) sections
    for chunking purposes, while this needs one row per individual
    numbered clause so a clause_number can be attached to each detected
    requirement."""
    matches = list(SECTION_HEADING_PATTERN.finditer(page_text))
    if not matches:
        return [(None, page_text)]

    clauses: list[tuple[str | None, str]] = []
    for i, match in enumerate(matches):
        clause_number = match.group(1)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(page_text)
        clauses.append((clause_number, page_text[start:end].strip()))
    return clauses
