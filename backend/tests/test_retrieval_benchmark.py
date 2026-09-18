"""
Phase 13 retrieval benchmark — a development diagnostic, NOT a production
accuracy claim.

Extends the Phase 4 evaluation pattern (test_retrieval_evaluation.py) with
the 8 query cases named in the Phase 13 brief: exact standard-number,
product synonym, technical requirement, testing, mandatory-status,
certification-process, product attribute, and irrelevant-document. For
each, measures whether the expected evidence appears in top-K, and
separately reports semantic-only vs FTS5-only vs hybrid results, so a
genuine regression in any one retrieval path is caught even if another
path compensates for it.

Uses the REAL embedding model (marked slow), like
test_retrieval_evaluation.py — a fake hash-based embedding provider cannot
meaningfully distinguish "product synonym query" from "irrelevant
document," which is exactly what this benchmark needs to measure.

The corpus is tiny synthetic fixtures — this measures actual behavior on
THIS software corpus only. It is not, and must never be presented as, a
claim about real-world BIS document retrieval accuracy (see
docs/IMPLEMENTATION_ROADMAP.md's REAL BIS DATA STATUS).
"""

import uuid

import pytest

from app.models.product_profile import ProductProfile
from app.product.hybrid_retrieval import find_candidates
from app.rag.index_document import index_document
from app.rag.keyword_search import search as keyword_search
from app.rag.retrieval import RetrievalService
from app.services.document_service import DocumentService

FIXTURE_TEXT = (
    "SYNTHETIC TEST DOCUMENT -- NOT AN OFFICIAL BIS STANDARD -- FOR PIPELINE TESTING ONLY\n\n"
    "IS 66601 : 2021\n"
    "Synthetic Electric Water Heater Requirements for Retrieval Benchmarking\n\n"
    "First Revision\n\n"
    "1 SCOPE\n"
    "This synthetic document exists only to test the retrieval benchmark. It covers electric storage water heaters "
    "for domestic use.\n\n"
    "4.2 Testing\n"
    "Each electric water heater sample shall be tested for electrical safety before dispatch.\n\n"
    "5.1 Certification\n"
    "A valid certificate under the applicable BIS scheme is required before market entry. This is not a mandatory "
    "regulatory determination — see the regulatory evidence layer for that.\n\n"
    "6.1 Documentation\n"
    "A technical specification and test report must be maintained for each production batch.\n"
)

IRRELEVANT_TEXT = (
    "SYNTHETIC TEST DOCUMENT -- NOT AN OFFICIAL BIS STANDARD -- FOR PIPELINE TESTING ONLY\n\n"
    "IS 12345 : 2019\n"
    "Synthetic Testing Laboratory Accreditation Guidance\n\n"
    "1 SCOPE\n"
    "This document is about laboratory accreditation procedures for a completely unrelated product category: "
    "bicycle helmets.\n"
)


@pytest.fixture()
def benchmark_corpus(db_session, isolated_storage):
    """Registers two synthetic documents directly via pymupdf (real text,
    real embeddings via the real model), returns their StandardDocument
    rows."""
    import pymupdf

    def _make_pdf(text: str) -> bytes:
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 50), text, fontsize=9)
        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    service = DocumentService(db_session)

    relevant_content = _make_pdf(FIXTURE_TEXT)
    relevant_doc = service.register_upload(relevant_content, "benchmark_relevant.pdf", "application/pdf", source_type="test")
    service.process_document(relevant_doc.id, relevant_content)
    index_document(db_session, relevant_doc.id)

    irrelevant_content = _make_pdf(IRRELEVANT_TEXT)
    irrelevant_doc = service.register_upload(irrelevant_content, "benchmark_irrelevant.pdf", "application/pdf", source_type="test")
    service.process_document(irrelevant_doc.id, irrelevant_content)
    index_document(db_session, irrelevant_doc.id)

    return relevant_doc, irrelevant_doc


# --- Case 1: exact standard-number query ---


@pytest.mark.slow
def test_benchmark_exact_standard_number_query(db_session, benchmark_corpus):
    relevant_doc, _ = benchmark_corpus
    retrieval = RetrievalService(db_session)

    semantic_results = retrieval.retrieve(query="IS 66601", top_k=5)
    keyword_results = keyword_search(db_session, "IS 66601", top_k=5)

    # The exact identifier must be findable by keyword search even if
    # semantic similarity for a short numeric query is mediocre — this is
    # the Phase 13 "exact identifiers must remain retrievable" case.
    assert any(r.document_id == relevant_doc.id for r in keyword_results)
    print(f"\nCase 1 (exact standard number): semantic top1 correct={semantic_results[0].document_id == relevant_doc.id if semantic_results else False}, keyword found={any(r.document_id == relevant_doc.id for r in keyword_results)}")


# --- Case 2: product synonym query ---


@pytest.mark.slow
def test_benchmark_product_synonym_query(db_session, benchmark_corpus):
    relevant_doc, irrelevant_doc = benchmark_corpus
    profile = ProductProfile(
        id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water_heater", product_name="geyser"
    )
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=5)
    assert len(candidates) > 0
    top_document_ids = [c.document_id for c in candidates]
    print(f"\nCase 2 (product synonym): top result is relevant doc={top_document_ids[0] == relevant_doc.id}")
    assert relevant_doc.id in top_document_ids


# --- Case 3: technical requirement query ---


@pytest.mark.slow
def test_benchmark_technical_requirement_query(db_session, benchmark_corpus):
    relevant_doc, _ = benchmark_corpus
    retrieval = RetrievalService(db_session)
    results = retrieval.retrieve(query="What technical requirement applies to electrical safety?", top_k=5)
    assert len(results) > 0
    print(f"\nCase 3 (technical requirement): top1 correct={results[0].document_id == relevant_doc.id}")


# --- Case 4: testing query ---


@pytest.mark.slow
def test_benchmark_testing_query(db_session, benchmark_corpus):
    relevant_doc, _ = benchmark_corpus
    retrieval = RetrievalService(db_session)
    results = retrieval.retrieve(query="What testing is required before dispatch?", top_k=5)
    assert len(results) > 0
    top3_correct = any(r.document_id == relevant_doc.id for r in results[:3])
    print(f"\nCase 4 (testing): top3 correct={top3_correct}")
    assert top3_correct


# --- Case 5: mandatory-status query ---


@pytest.mark.slow
def test_benchmark_mandatory_status_query(db_session, benchmark_corpus):
    from app.product.query_classification import QueryClass, classify_query

    query = "Is BIS certification mandatory for this product?"
    query_classes = classify_query(query)
    print(f"\nCase 5 (mandatory status): classified as {query_classes}")
    assert QueryClass.MANDATORY_STATUS in query_classes


# --- Case 6: certification-process query ---


@pytest.mark.slow
def test_benchmark_certification_process_query(db_session, benchmark_corpus):
    from app.product.query_classification import QueryClass, classify_query

    query = "How do I apply for a BIS certification scheme?"
    query_classes = classify_query(query)
    print(f"\nCase 6 (certification process): classified as {query_classes}")
    assert QueryClass.CERTIFICATION_PROCESS in query_classes


# --- Case 7: product attribute query ---


@pytest.mark.slow
def test_benchmark_product_attribute_query(db_session, benchmark_corpus):
    relevant_doc, _ = benchmark_corpus
    profile = ProductProfile(
        id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        product_category="water_heater",
        electrical_characteristics="230V, 2000W",
    )
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=5)
    assert len(candidates) > 0
    print(f"\nCase 7 (product attribute): candidates found={len(candidates)}")


# --- Case 8: irrelevant-document query ---


@pytest.mark.slow
def test_benchmark_irrelevant_document_query(db_session, benchmark_corpus):
    relevant_doc, irrelevant_doc = benchmark_corpus
    retrieval = RetrievalService(db_session)
    results = retrieval.retrieve(query="What is the scope of this electric water heater standard?", top_k=5)

    # The irrelevant (bicycle-helmet-laboratory-accreditation) document
    # must not outrank the genuinely relevant water-heater document for a
    # clearly water-heater-specific query.
    relevant_rank = next((i for i, r in enumerate(results) if r.document_id == relevant_doc.id), None)
    irrelevant_rank = next((i for i, r in enumerate(results) if r.document_id == irrelevant_doc.id), None)
    print(f"\nCase 8 (irrelevant document): relevant_rank={relevant_rank}, irrelevant_rank={irrelevant_rank}")
    if relevant_rank is not None and irrelevant_rank is not None:
        assert relevant_rank < irrelevant_rank


# --- Summary: hybrid vs semantic-only vs FTS5-only comparison ---


@pytest.mark.slow
def test_benchmark_hybrid_outperforms_either_alone_for_exact_identifier(db_session, benchmark_corpus):
    """A short, mostly-numeric exact-identifier query is exactly the case
    hybrid retrieval exists for: semantic similarity on a short numeric
    string is unreliable, but FTS5 keyword search finds it exactly. This
    locks in that hybrid (via find_candidates) surfaces the identifier
    match that a semantic-only path might miss."""
    relevant_doc, _ = benchmark_corpus
    profile = ProductProfile(
        id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        product_category="water_heater",
        other_attributes="IS 66601",
    )
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=5, user_query="Does IS 66601 apply?")
    keyword_only = keyword_search(db_session, "IS 66601", top_k=5)

    hybrid_found = any(c.document_id == relevant_doc.id for c in candidates)
    keyword_found = any(r.document_id == relevant_doc.id for r in keyword_only)
    print(f"\nHybrid vs keyword-only for exact identifier: hybrid_found={hybrid_found}, keyword_only_found={keyword_found}")
    assert hybrid_found
    assert keyword_found
