"""
Query classification — Phase 12, extended in Phase 13.

Given a query's text, suggests which DocumentType values are most likely
to hold the answer — a small, deterministic keyword classifier, not an
LLM call or an ML model. Used by app/product/hybrid_retrieval.py to boost
(not hard-filter) semantic-search relevance for documents of a
prioritized type, so a regulatory-sounding question ("is certification
mandatory?") is more likely to surface REGULATORY_ORDER/QCO/
CERTIFICATION_GUIDANCE evidence over an ordinary INDIAN_STANDARD, without
ever excluding other types outright.

A soft boost, not a hard filter, because most documents in this project
have document_type="OTHER" (the default — see
app/product/document_type.py) since classification is optional and
user-asserted at upload time; a hard filter would silently break existing
retrieval for every document that predates or skips explicit
classification. This mirrors Phase 10/11's own "never let a rigid rule
silently exclude potentially relevant evidence" principle.

Phase 13 names the underlying query "objective" explicitly as a QueryClass
enum (TECHNICAL_REQUIREMENT, TESTING, CERTIFICATION_PROCESS,
MANDATORY_STATUS, DOCUMENTATION, GENERAL_PRODUCT_STANDARD) — still pure
regex classification, never LLM-mandatory for retrieval to function.
prioritized_document_types() is kept unchanged in behavior/signature (it's
already used by hybrid_retrieval.py's sort key) and is now implemented in
terms of classify_query()/QUERY_CLASS_DOCUMENT_TYPES, so both entry points
stay consistent with a single source of truth.
"""

import re
from enum import Enum

from app.product.document_type import DocumentType, PROCEDURAL_DOCUMENT_TYPES, REGULATORY_DOCUMENT_TYPES, TECHNICAL_DOCUMENT_TYPES


class QueryClass(str, Enum):
    TECHNICAL_REQUIREMENT = "TECHNICAL_REQUIREMENT"
    TESTING = "TESTING"
    CERTIFICATION_PROCESS = "CERTIFICATION_PROCESS"
    MANDATORY_STATUS = "MANDATORY_STATUS"
    DOCUMENTATION = "DOCUMENTATION"
    GENERAL_PRODUCT_STANDARD = "GENERAL_PRODUCT_STANDARD"


_MANDATORY_STATUS_PATTERN = re.compile(
    r"\b(mandatory|compulsory|qco|quality control order|regulation|regulatory|legally required|law)\b",
    re.IGNORECASE,
)
_CERTIFICATION_PROCESS_PATTERN = re.compile(
    r"\b(how do i apply|how to apply|application process|apply for|procedure|application form|scheme|certificate)\b",
    re.IGNORECASE,
)
_TESTING_PATTERN = re.compile(
    r"\b(test method|tested|testing|sample shall be|laboratory)\b",
    re.IGNORECASE,
)
_DOCUMENTATION_PATTERN = re.compile(
    r"\b(technical specification|drawing|bill of materials|test report|documentation|records? (?:required|needed))\b",
    re.IGNORECASE,
)
_TECHNICAL_REQUIREMENT_PATTERN = re.compile(
    r"\b(technical requirement|specification|requirement applies|clause|parameter)\b",
    re.IGNORECASE,
)

# Kept as backward-compatible aliases for existing callers/tests written
# against Phase 12's 3-pattern names.
_REGULATORY_QUERY_PATTERN = _MANDATORY_STATUS_PATTERN
_PROCEDURAL_QUERY_PATTERN = _CERTIFICATION_PROCESS_PATTERN
_TECHNICAL_QUERY_PATTERN = _TECHNICAL_REQUIREMENT_PATTERN

# Ordered: a query can match more than one class's pattern (e.g. "what
# testing documentation is required" matches both TESTING and
# DOCUMENTATION) — classify_query() returns every match, in this priority
# order, so callers that want a single "primary" class can take the first
# element rather than this module guessing which one the user meant most.
_CLASS_PATTERNS: list[tuple[QueryClass, re.Pattern]] = [
    (QueryClass.MANDATORY_STATUS, _MANDATORY_STATUS_PATTERN),
    (QueryClass.CERTIFICATION_PROCESS, _CERTIFICATION_PROCESS_PATTERN),
    (QueryClass.TESTING, _TESTING_PATTERN),
    (QueryClass.DOCUMENTATION, _DOCUMENTATION_PATTERN),
    (QueryClass.TECHNICAL_REQUIREMENT, _TECHNICAL_REQUIREMENT_PATTERN),
]

QUERY_CLASS_DOCUMENT_TYPES: dict[QueryClass, set[str]] = {
    QueryClass.MANDATORY_STATUS: REGULATORY_DOCUMENT_TYPES,
    QueryClass.CERTIFICATION_PROCESS: PROCEDURAL_DOCUMENT_TYPES,
    QueryClass.TESTING: {DocumentType.TESTING_GUIDANCE.value, DocumentType.INDIAN_STANDARD.value},
    QueryClass.DOCUMENTATION: {DocumentType.CERTIFICATION_GUIDANCE.value, DocumentType.BIS_SCHEME.value},
    QueryClass.TECHNICAL_REQUIREMENT: TECHNICAL_DOCUMENT_TYPES,
    QueryClass.GENERAL_PRODUCT_STANDARD: set(),
}


def classify_query(query: str) -> list[QueryClass]:
    """Returns every QueryClass whose pattern matches this query's text,
    in priority order (see _CLASS_PATTERNS). Returns
    [GENERAL_PRODUCT_STANDARD] — never an empty list — when nothing more
    specific matches, since every query has at least a general objective
    (find product-relevant standard evidence)."""
    matched = [query_class for query_class, pattern in _CLASS_PATTERNS if pattern.search(query)]
    return matched or [QueryClass.GENERAL_PRODUCT_STANDARD]


def prioritized_document_types(query: str) -> set[str]:
    """Returns the set of DocumentType values to prioritize (boost, not
    exclude) for this query's text. Returns an empty set when the query
    doesn't match any recognized pattern — callers must treat that as "no
    priority signal," not as "prioritize nothing" in a way that excludes
    results. Implemented in terms of classify_query() so both entry points
    share one source of truth."""
    prioritized: set[str] = set()
    for query_class in classify_query(query):
        prioritized |= QUERY_CLASS_DOCUMENT_TYPES.get(query_class, set())
    return prioritized
