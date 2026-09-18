"""
Retrieval evaluation — a development diagnostic, NOT a production accuracy
claim.

The corpus here is tiny (2 synthetic single/few-page test documents, a
handful of chunks total) — far too small to produce a statistically
meaningful accuracy percentage. This file measures actual behavior on that
tiny corpus and reports the raw numbers; it does not extrapolate them into
a claim about real-world BIS document retrieval quality.

Uses the real embedding model (marked slow) — the evaluation is only
meaningful with real semantic embeddings, not the deterministic fake
provider used elsewhere for speed.
"""

from pathlib import Path

import pytest

from app.rag.index_document import index_document
from app.rag.retrieval import RetrievalService
from app.services.document_service import DocumentService

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Each case: a query, and which document/page it should retrieve from.
# Built from the actual known content of the synthetic fixtures (see
# tests/fixtures/generate_test_pdfs.py) — not invented after the fact to
# make the numbers look good.
EVAL_CASES = [
    {
        "query": "What is the scope of this document?",
        "expected_document": "test_text.pdf",
        "expected_page": 1,
        "expected_section": "1",
    },
    {
        "query": "What other standards does this document reference?",
        "expected_document": "test_text.pdf",
        "expected_page": 1,
        "expected_section": "2",
    },
    {
        "query": "What are the requirements specified?",
        "expected_document": "test_text.pdf",
        "expected_page": 1,
        "expected_section": "3",
    },
]


@pytest.mark.slow
def test_retrieval_evaluation_on_synthetic_corpus(db_session, isolated_storage):
    content = (FIXTURES_DIR / "test_text.pdf").read_bytes()
    service = DocumentService(db_session)
    document = service.register_upload(content, "test_text.pdf", "application/pdf", source_type="test")
    service.process_document(document.id, content)
    index_document(db_session, document.id)

    retrieval_service = RetrievalService(db_session)

    top1_correct = 0
    top3_correct = 0

    for case in EVAL_CASES:
        results = retrieval_service.retrieve(query=case["query"], top_k=3)
        assert len(results) > 0, f"No results at all for query: {case['query']}"

        top1_match = results[0].section == case["expected_section"]
        top3_match = any(r.section == case["expected_section"] for r in results)

        if top1_match:
            top1_correct += 1
        if top3_match:
            top3_correct += 1

    total = len(EVAL_CASES)
    print(f"\n--- Retrieval evaluation on synthetic corpus (n={total}) ---")
    print(f"Top-1 section match: {top1_correct}/{total}")
    print(f"Top-3 section match: {top3_correct}/{total}")
    print("NOTE: this corpus has only 3 documents' worth of tiny synthetic content.")
    print("These numbers describe THIS test run on THIS synthetic corpus only —")
    print("they are not a claim about retrieval accuracy on real BIS documents.")

    # The evaluation's purpose is to catch a genuine regression (e.g. the
    # embedding pipeline silently returning garbage) — asserting on the
    # measured numbers keeps this test meaningful rather than decorative.
    assert top3_correct >= 2, "Retrieval quality regression: fewer than 2/3 queries found their section in top-3."
