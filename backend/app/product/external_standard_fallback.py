"""
External standard fallback (query-time) — when local retrieval finds
nothing usable for a product, search Internet Archive's real Indian
Standards index (app.ingestion.archive_org_client) for a match, ingest it
through the exact same DocumentService pipeline a UI upload uses, and let
the caller re-run local retrieval so the new document is found the normal
way.

This exists specifically so the assistant is not stuck saying "nothing
found" for a product whose relevant standard simply was not in the local
database yet — the assistant's day-1 knowledge base is the ~6-and-growing
set of documents ingested so far, not the ~22,700 real standards this
project could in principle draw on.

Deliberately NOT a general web-search-and-answer fallback: every fact the
assistant states must still trace back to a real, ingested, retrievable
BIS document (see app/product/response_safety.py) — this module's only
job is to get a real document INTO the database before retrieval runs
again, never to hand raw search results or web text to the LLM directly.

Trigger condition (see should_attempt_fallback): local retrieval produced
either no candidates at all, or only candidates whose final_score is below
FALLBACK_SCORE_THRESHOLD — i.e. genuinely nothing relevant, not merely "the
best candidate isn't a perfect match." A profile with no usable search
terms yet (see app.product.search_terms.derive_search_terms) never
triggers this — there is nothing meaningful to search Internet Archive for
either.
"""

import logging

from sqlalchemy.orm import Session

from app.ingestion.archive_org_client import ArchiveOrgError, fetch_pdf, search_standards
from app.product.search_terms import derive_search_terms
from app.schemas.candidate_standard import ApplicabilityStatus
from app.services.document_service import DocumentService, DuplicateDocumentError

logger = logging.getLogger("bis_sahayak")

MAX_EXTERNAL_RESULTS_TO_TRY = 3


def should_attempt_fallback(candidates: list, profile) -> bool:
    """Deliberately NOT based on final_score: that score is normalized
    relative to whatever pool retrieval happened to return (see
    app/product/scoring.py's min_max_normalize), so even a pool of
    entirely irrelevant documents always has a "best of the pool" near
    1.0 — confirmed by testing this fallback against a real product
    category (water purifiers) with nothing locally relevant, where the
    top (still irrelevant) candidate's final_score came out at 0.45, well
    above any reasonable-looking score threshold. The actual honest
    signal for "nothing relevant was found" is applicability.py's own
    rule-based determination: every candidate sitting at
    NEEDS_CLARIFICATION with none reaching POTENTIALLY_APPLICABLE/
    APPLICABLE means no candidate's evidence text actually mentioned the
    product — which is exactly the condition this fallback exists for."""
    if not derive_search_terms(profile):
        return False
    if not candidates:
        return True
    return not any(
        c.applicability_status in (ApplicabilityStatus.POTENTIALLY_APPLICABLE, ApplicabilityStatus.APPLICABLE)
        for c in candidates
    )


def try_ingest_external_match(db: Session, profile) -> str | None:
    """Searches Internet Archive for a standard matching the profile's
    derived search terms, ingests the first one that downloads and
    processes successfully, and returns its new document_id — or None if
    no external match was found or every candidate failed to ingest (e.g.
    a network error, or the item has no PDF). Never raises: a fallback
    failing must degrade to the existing "needs clarification" behavior,
    not break the chat turn."""
    # Deliberately NOT derive_search_terms()'s full output: that list is
    # tuned for local keyword/semantic search (which benefits from
    # including the normalized taxonomy slug, e.g. "water_purifier",
    # alongside natural-language terms). Internet Archive's search matches
    # literal words in real, human-written standard titles — an
    # underscored taxonomy slug will never appear in one, and
    # AND-ing together every derived term (Internet Archive's title:(...)
    # syntax requires ALL listed words to match) makes the query so
    # over-constrained it matches nothing. Confirmed by testing: searching
    # for "RO water purifier water_purifier reverse osmosis water
    # purifier" returned zero results, while "reverse osmosis" alone
    # correctly found IS 16240 (Reverse Osmosis Based Point of Use Water
    # Treatment System). product_type is the most specific natural-language
    # description available on the profile; product_name/product_category
    # are used only if product_type is not yet known.
    query = profile.product_type or profile.product_name or profile.product_category
    if not query:
        return None

    try:
        results = search_standards(query, max_results=MAX_EXTERNAL_RESULTS_TO_TRY)
    except Exception as exc:  # noqa: BLE001 — a search failure must degrade gracefully, not break the chat turn
        logger.warning("External standard search failed for query %r: %s", query, exc)
        return None

    if not results:
        return None

    service = DocumentService(db)
    for result in results:
        try:
            pdf_bytes = fetch_pdf(result.identifier)
        except ArchiveOrgError as exc:
            logger.warning("Could not fetch external standard %s: %s", result.identifier, exc)
            continue

        try:
            document = service.register_upload(
                content=pdf_bytes,
                filename=f"{result.identifier}.pdf",
                mime_type="application/pdf",
                document_type="INDIAN_STANDARD",
                source="internet_archive_fallback",
            )
        except DuplicateDocumentError:
            # Already ingested (e.g. a previous fallback or bulk-download
            # run already brought this exact file in) — nothing new to do,
            # but not a failure either; the caller's re-run of local
            # retrieval will find it regardless.
            return None
        except Exception as exc:  # noqa: BLE001 — one bad candidate must not abort trying the next
            logger.warning("Could not register external standard %s: %s", result.identifier, exc)
            continue

        processed = service.process_document(document.id, pdf_bytes)
        if processed.status != "completed":
            logger.warning(
                "External standard %s ingested but pipeline did not complete: %s",
                result.identifier,
                processed.error_message,
            )
            continue

        logger.info(
            "External standard fallback: ingested %s (%s) for query %r",
            result.identifier,
            result.title,
            query,
        )
        return processed.id

    return None
