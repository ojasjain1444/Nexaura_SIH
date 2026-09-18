"""
Score normalization and reranking — Phase 13.

Fixes a confirmed gap in the Phase 10 hybrid merge (see
app/product/hybrid_retrieval.py): raw cosine similarity ([-1, 1], higher
is better) and raw SQLite FTS5 bm25() scores (unbounded, MORE NEGATIVE is
better) were never normalized or combined arithmetically — a
CandidateStandard's relevance_score was simply the max cosine similarity
across its evidence, and a chunk found ONLY by keyword search was assigned
similarity_score=0.0, sinking it below even a weak semantic match
regardless of how strong its actual keyword relevance was.

This module normalizes each score type independently to [0, 1] within its
own result set (min-max scaling — deterministic, no learned parameters,
no ML model), then combines normalized components as an explicit, small,
named weighted sum. Every weight is a module-level constant with a
one-line rationale — "explainable," per the Phase 13 brief, means a human
can read this file and understand exactly why a candidate ranked where it
did, not that the system exposes its internals to end users (it does not
— RankedEvidence's component scores are for developer/debugging use only,
per app/schemas/candidate_standard.py's CandidateStandard fields, which
remain the only user-facing shape).

This is NOT a learned reranking model and NOT a paid API — explicitly
required to stay that way per the Phase 13 brief ("prefer deterministic
scoring first").
"""

from dataclasses import dataclass

# Small, named weights — kept low relative to each other so no single
# signal can dominate the total ordering by itself; boosts nudge rank
# rather than override the underlying retrieval evidence.
WEIGHT_SEMANTIC = 0.45
WEIGHT_KEYWORD = 0.35
WEIGHT_DOCUMENT_TYPE_BOOST = 0.10
WEIGHT_EXACT_IDENTIFIER_MATCH = 0.20
WEIGHT_PROFILE_ATTRIBUTE_MATCH = 0.10

# Fixed boost amounts (already in the same [0, 1] final-score space) —
# applied additively, capped by the weight above, never multiplied in a
# way that could let a boost alone exceed a genuine top-ranked match.
DOCUMENT_TYPE_BOOST_VALUE = 1.0
EXACT_IDENTIFIER_BOOST_VALUE = 1.0
PROFILE_ATTRIBUTE_BOOST_VALUE = 1.0


@dataclass
class ScoreBreakdown:
    """Debug/explanation data for one candidate's ranking — never surfaced
    to end users in chat prose (see app/product/discovery_response.py's
    existing rule against the LLM inventing its own relevance
    explanations); this exists so a developer/test can answer "why did
    this rank where it did.\""""

    semantic_score: float | None  # raw cosine similarity, or None if no semantic match contributed
    keyword_score: float | None  # raw bm25 score, or None if no keyword match contributed
    normalized_semantic: float
    normalized_keyword: float
    document_type_boost: float
    exact_identifier_boost: float
    profile_attribute_boost: float
    final_score: float


def min_max_normalize(values: list[float], reverse: bool = False) -> list[float]:
    """Min-max scales `values` to [0, 1]. `reverse=True` inverts the sense
    first (for bm25, where MORE NEGATIVE is better — see module docstring)
    so that, after this call, higher always means better in every
    normalized score this module produces. A single-element or
    all-identical list normalizes to 1.0 for every element (there is no
    meaningful spread to rank within) rather than dividing by zero."""
    if not values:
        return []
    working = [-v for v in values] if reverse else list(values)
    lo, hi = min(working), max(working)
    if hi == lo:
        return [1.0 for _ in working]
    return [(v - lo) / (hi - lo) for v in working]


def compute_final_score(
    normalized_semantic: float,
    normalized_keyword: float,
    document_type_matched: bool,
    exact_identifier_matched: bool,
    profile_attribute_matched: bool,
) -> ScoreBreakdown:
    """Combines already-normalized component scores into one explainable
    final_score via a fixed weighted sum. Boost terms are boolean-gated
    (matched or not), not scaled by anything else — keeping the formula a
    single, auditable line rather than a chain of multiplicative
    adjustments that would be hard to reason about."""
    document_type_boost = DOCUMENT_TYPE_BOOST_VALUE if document_type_matched else 0.0
    exact_identifier_boost = EXACT_IDENTIFIER_BOOST_VALUE if exact_identifier_matched else 0.0
    profile_attribute_boost = PROFILE_ATTRIBUTE_BOOST_VALUE if profile_attribute_matched else 0.0

    final_score = (
        WEIGHT_SEMANTIC * normalized_semantic
        + WEIGHT_KEYWORD * normalized_keyword
        + WEIGHT_DOCUMENT_TYPE_BOOST * document_type_boost
        + WEIGHT_EXACT_IDENTIFIER_MATCH * exact_identifier_boost
        + WEIGHT_PROFILE_ATTRIBUTE_MATCH * profile_attribute_boost
    )

    return ScoreBreakdown(
        semantic_score=None,
        keyword_score=None,
        normalized_semantic=normalized_semantic,
        normalized_keyword=normalized_keyword,
        document_type_boost=document_type_boost,
        exact_identifier_boost=exact_identifier_boost,
        profile_attribute_boost=profile_attribute_boost,
        final_score=final_score,
    )
