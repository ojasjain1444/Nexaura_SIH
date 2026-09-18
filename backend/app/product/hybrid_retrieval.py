"""
HybridRetrievalService — Phase 10, reranking added in Phase 13.

Combines the existing semantic RetrievalService (unchanged, Phase 4/5) with
the lexical KeywordSearchService (Phase 10, app/rag/keyword_search.py) to
produce CandidateStandard objects for product-discovery flows.

Architecture (Phase 13):

    ProductProfile -> search terms (+ exact identifiers)
                          -> semantic search (wide pool)
                          -> keyword search (wide pool)
                          -> merge by chunk_id
                          -> group by document
                          -> normalize scores, compute final_score
                          -> sort by final_score
                          -> CandidateStandard (applicability not yet
                             evaluated — see app/product/applicability.py)

This does not replace or modify RetrievalService/LocalVectorStore in any
way — it is a new, additive caller of the existing retrieve() method,
exactly as app/services/chat_service.py already is. Plain BIS chat (Phase
5) continues to call RetrievalService directly and is completely
unaffected by this module's existence.

Phase 10/12 confirmed gap fixed here: raw cosine similarity and raw bm25
scores were never normalized or combined arithmetically — a keyword-only
match was scored similarity_score=0.0 and effectively sank to the bottom
regardless of how strong its actual keyword relevance was. Phase 13 fixes
this via app/product/scoring.py's min-max normalization + explicit
weighted sum, applied independently within THIS query's result set (never
across queries — there's no persisted global score distribution to
normalize against, which would be a much bigger, unjustified change).
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.standard_document import StandardDocument
from app.product.query_classification import prioritized_document_types
from app.product.scoring import compute_final_score, min_max_normalize
from app.product.search_terms import build_query_text, derive_search_terms, extract_exact_identifiers
from app.rag import keyword_search
from app.rag.retrieval import RetrievalService
from app.schemas.candidate_standard import ApplicabilityStatus, CandidateStandard
from app.schemas.retrieval import RetrievedChunk

# Widened candidate pools per the Phase 13 brief ("retrieve a reasonable
# candidate pool from each... do not immediately restrict to top 4") —
# these feed reranking, which then trims to the caller's requested top_k
# as the FINAL step, not the first one.
SEMANTIC_POOL_SIZE = 20
KEYWORD_POOL_SIZE = 20


@dataclass
class _MergedEvidence:
    chunk: RetrievedChunk
    matched_terms: list[str]
    found_semantically: bool
    found_lexically: bool
    semantic_score: float | None = None  # raw cosine similarity, if found semantically
    keyword_score: float | None = None  # raw bm25 score, if found lexically
    exact_identifier_matched: bool = False


def _keyword_matches_for_terms(
    db: Session, terms: list[str], top_k: int
) -> dict[str, tuple[keyword_search.KeywordMatch, str]]:
    """Runs one keyword search per term (terms are short and few — a
    handful of profile-derived phrases, not a large query set) and returns
    the best-scoring match per chunk_id along with which term matched it."""
    best_by_chunk: dict[str, tuple[keyword_search.KeywordMatch, str]] = {}
    for term in terms:
        try:
            matches = keyword_search.search(db, term, top_k=top_k)
        except keyword_search.KeywordSearchError:
            continue  # a malformed FTS query for one term must not abort the whole search
        for match in matches:
            existing = best_by_chunk.get(match.chunk_id)
            if existing is None or match.bm25_score < existing[0].bm25_score:  # more negative bm25 = better
                best_by_chunk[match.chunk_id] = (match, term)
    return best_by_chunk


def _merge_semantic_and_keyword_evidence(
    db: Session,
    semantic_chunks: list[RetrievedChunk],
    keyword_matches: dict[str, tuple[keyword_search.KeywordMatch, str]],
    exact_identifiers: list[str],
) -> dict[str, _MergedEvidence]:
    merged: dict[str, _MergedEvidence] = {
        chunk.chunk_id: _MergedEvidence(
            chunk=chunk,
            matched_terms=[],
            found_semantically=True,
            found_lexically=False,
            semantic_score=chunk.similarity_score,
            exact_identifier_matched=_text_contains_any(chunk.text, exact_identifiers),
        )
        for chunk in semantic_chunks
    }

    for chunk_id, (match, term) in keyword_matches.items():
        if chunk_id in merged:
            merged[chunk_id].found_lexically = True
            merged[chunk_id].keyword_score = match.bm25_score
            if term not in merged[chunk_id].matched_terms:
                merged[chunk_id].matched_terms.append(term)
            continue

        # A keyword-only match needs its real page_number/section, which
        # the FTS table doesn't carry (see keyword_search.py) — looked up
        # from the actual DocumentChunk row rather than defaulted to a
        # placeholder like page 0, which would be a fabricated citation
        # field.
        document = db.get(StandardDocument, match.document_id)
        chunk_row = db.get(DocumentChunk, match.chunk_id)
        if document is None or chunk_row is None:
            continue
        chunk = RetrievedChunk(
            chunk_id=match.chunk_id,
            document_id=match.document_id,
            document_name=document.original_filename,
            document_type=document.document_type,
            page_number=chunk_row.page_number,
            section=chunk_row.section,
            text=match.text,
            similarity_score=0.0,  # not a semantic match — no cosine score to report; excluded from normalization below
        )
        merged[chunk_id] = _MergedEvidence(
            chunk=chunk,
            matched_terms=[term],
            found_semantically=False,
            found_lexically=True,
            keyword_score=match.bm25_score,
            exact_identifier_matched=_text_contains_any(chunk.text, exact_identifiers),
        )
    return merged


def _text_contains_any(text: str, identifiers: list[str]) -> bool:
    if not identifiers:
        return False
    lowered = text.lower()
    return any(identifier.lower() in lowered for identifier in identifiers)


def _profile_matches_evidence_text(profile, text: str) -> bool:
    """True if any stated ProductProfile attribute (category/type/
    technology) appears verbatim in this evidence text — a light,
    deterministic signal that the evidence actually concerns the user's
    stated product, distinct from applicability.py's own (separate, more
    authoritative) category/type check used for APPLICABLE/
    POTENTIALLY_APPLICABLE determination. This is only a ranking boost,
    never an applicability determination."""
    lowered = text.lower()
    for attribute in (profile.product_category, profile.product_type, profile.technology):
        if attribute and attribute.lower() in lowered:
            return True
    return False


def _rerank(
    by_document: dict[str, list[_MergedEvidence]],
    db: Session,
    profile,
    priority_types: set[str],
    top_k: int,
) -> list[CandidateStandard]:
    """Normalizes scores within this result set and computes each
    document's final_score via app/product/scoring.py's weighted sum, then
    sorts descending. Normalization is deliberately scoped to THIS call's
    result set only (see module docstring) — there is no cross-query score
    history to normalize against."""
    all_semantic = [e.semantic_score for evidences in by_document.values() for e in evidences if e.semantic_score is not None]
    all_keyword = [e.keyword_score for evidences in by_document.values() for e in evidences if e.keyword_score is not None]

    # Building lookup maps from raw score -> normalized score is safe here
    # because min_max_normalize preserves list order and we zip back
    # against the same source lists — no dictionary keyed by float value
    # (which would collide on ties) is used.
    normalized_semantic_lookup = dict(zip(all_semantic, min_max_normalize(all_semantic)))
    normalized_keyword_lookup = dict(zip(all_keyword, min_max_normalize(all_keyword, reverse=True)))

    candidates: list[CandidateStandard] = []
    for document_id, evidences in by_document.items():
        document = db.get(StandardDocument, document_id)
        if document is None:
            continue

        best_normalized_semantic = max(
            (normalized_semantic_lookup[e.semantic_score] for e in evidences if e.semantic_score is not None),
            default=0.0,
        )
        best_normalized_keyword = max(
            (normalized_keyword_lookup[e.keyword_score] for e in evidences if e.keyword_score is not None),
            default=0.0,
        )
        document_type_matched = document.document_type in priority_types
        exact_identifier_matched = any(e.exact_identifier_matched for e in evidences)
        profile_attribute_matched = any(_profile_matches_evidence_text(profile, e.chunk.text) for e in evidences)

        breakdown = compute_final_score(
            normalized_semantic=best_normalized_semantic,
            normalized_keyword=best_normalized_keyword,
            document_type_matched=document_type_matched,
            exact_identifier_matched=exact_identifier_matched,
            profile_attribute_matched=profile_attribute_matched,
        )

        # Evidence ordering within a candidate: strongest combination of
        # semantic+keyword first, matching how the top-level sort works —
        # a reader inspecting evidence[0] sees the strongest single chunk.
        evidences_sorted = sorted(
            evidences,
            key=lambda e: (
                (normalized_semantic_lookup.get(e.semantic_score, 0.0) if e.semantic_score is not None else 0.0)
                + (normalized_keyword_lookup.get(e.keyword_score, 0.0) if e.keyword_score is not None else 0.0)
            ),
            reverse=True,
        )
        all_terms = sorted({term for e in evidences for term in e.matched_terms})

        candidates.append(
            CandidateStandard(
                document_id=document_id,
                standard_id=document.standard_id,
                document_name=document.original_filename,
                relevance_score=breakdown.final_score,
                matched_terms=all_terms,
                evidence=[e.chunk for e in evidences_sorted[:top_k]],
                applicability_status=ApplicabilityStatus.NEEDS_CLARIFICATION,
                applicability_reason="Applicability not yet evaluated.",
                semantic_score=max((e.semantic_score for e in evidences if e.semantic_score is not None), default=None),
                keyword_score=min((e.keyword_score for e in evidences if e.keyword_score is not None), default=None),
                document_type_boost=breakdown.document_type_boost,
                exact_identifier_boost=breakdown.exact_identifier_boost,
                profile_attribute_boost=breakdown.profile_attribute_boost,
                final_score=breakdown.final_score,
            )
        )

    candidates.sort(key=lambda c: c.final_score or 0.0, reverse=True)
    return candidates[:top_k]


def find_candidates(
    db: Session,
    profile,
    top_k: int = 8,
    standard_id: str | None = None,
    user_query: str | None = None,
) -> list[CandidateStandard]:
    """Produces CandidateStandard objects (applicability_status always
    NEEDS_CLARIFICATION at this stage — see applicability.py for the actual
    determination step) from a ProductProfile's derived search terms plus
    any exact standard identifiers mentioned in the profile or user_query.
    Returns [] if the profile has no usable search terms AND no exact
    identifiers, rather than running a meaningless empty-query search.

    Phase 13: retrieves a wide candidate pool from each of semantic and
    keyword search (SEMANTIC_POOL_SIZE/KEYWORD_POOL_SIZE), merges and
    reranks via app/product/scoring.py's normalized weighted sum, and only
    THEN trims to top_k — never restricting to top_k before reranking has
    a full pool to work with.

    `user_query` (the raw user message, distinct from the profile-derived
    search terms used for the actual retrieval query) is passed through
    app/product/query_classification.py to determine which document_types
    to prioritize — a soft re-ranking boost only, never a hard filter."""
    terms = derive_search_terms(profile)
    exact_identifiers = extract_exact_identifiers(user_query or "") + extract_exact_identifiers(
        profile.other_attributes or ""
    )
    if not terms and not exact_identifiers:
        return []

    retrieval_service = RetrievalService(db)
    query_text = build_query_text(profile) or " ".join(exact_identifiers)
    try:
        semantic_chunks = retrieval_service.retrieve(query=query_text, top_k=SEMANTIC_POOL_SIZE, standard_id=standard_id)
    except Exception:
        semantic_chunks = []  # semantic retrieval failing must not prevent keyword-only candidates

    # Exact identifiers are searched as their own guaranteed keyword-search
    # terms, in addition to (never instead of) the profile-derived terms —
    # per the Phase 13 brief, an identifier like "IS 4001:2021" must remain
    # independently searchable verbatim, not diluted into general terms.
    keyword_matches = _keyword_matches_for_terms(db, terms + exact_identifiers, top_k=KEYWORD_POOL_SIZE)
    merged = _merge_semantic_and_keyword_evidence(db, semantic_chunks, keyword_matches, exact_identifiers)

    # Group merged evidence by document, since a CandidateStandard
    # represents "this document, as a whole, given this evidence" — not one
    # candidate per chunk.
    by_document: dict[str, list[_MergedEvidence]] = {}
    for evidence in merged.values():
        by_document.setdefault(evidence.chunk.document_id, []).append(evidence)

    priority_types = prioritized_document_types(user_query) if user_query else set()
    return _rerank(by_document, db, profile, priority_types, top_k)
