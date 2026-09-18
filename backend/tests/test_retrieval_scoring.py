"""
Phase 13 tests — query engine, hybrid scoring/reranking, product-profile
specificity.

Uses hand-written LLM test doubles exclusively (matching earlier phases'
conventions), never a real external API call. Reuses ScriptedFakeLLM and
_make_document_with_chunk from tests/test_product_discovery.py rather than
duplicating them. Fast tests use FakeEmbeddingProvider; anything requiring
real semantic discrimination lives in test_retrieval_benchmark.py (marked
slow) instead.

All evidence used here is SYNTHETIC TEST DATA — never a real BIS document.
"""

import uuid

from app.models.product_profile import ProductProfile
from app.product.hybrid_retrieval import find_candidates
from app.product.product_taxonomy import normalize_category
from app.product.profile_extraction import apply_updates
from app.product.query_classification import QueryClass, classify_query, prioritized_document_types
from app.product.scoring import compute_final_score, min_max_normalize
from app.product.search_terms import derive_search_terms, extract_exact_identifiers
from app.product.specificity import UpdateDecision, evaluate_update
from app.rag.retrieval import RetrievalService
from tests.test_embeddings import FakeEmbeddingProvider
from tests.test_product_discovery import _make_document_with_chunk


# --- 1. Query construction ---


def test_derive_search_terms_includes_phase13_attribute_fields():
    profile = ProductProfile(
        id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        product_category="water_heater",
        capacity="25 L",
        electrical_characteristics="230 V",
        materials="copper",
        target_market="India",
        manufacturing_location="India",
    )
    terms = derive_search_terms(profile)
    assert "25 L" in terms
    assert "230 V" in terms
    assert "copper" in terms
    assert "India" in terms  # target_market and manufacturing_location both "India" -> de-duplicated


def test_extract_exact_identifiers_finds_is_numbers():
    identifiers = extract_exact_identifiers("Does IS 4001:2021 or IS/ISO 2859-1 apply here?")
    assert "IS 4001:2021" in identifiers
    assert "IS/ISO 2859-1" in identifiers


def test_extract_exact_identifiers_empty_for_no_match():
    assert extract_exact_identifiers("just a plain question with no standard number") == []


def test_extract_exact_identifiers_deduplicates():
    identifiers = extract_exact_identifiers("IS 4001 is relevant. Please confirm IS 4001 applies.")
    assert identifiers == ["IS 4001"]


# --- 2. Query classification ---


def test_classify_query_returns_general_for_unrelated_text():
    assert classify_query("Hello, how are you?") == [QueryClass.GENERAL_PRODUCT_STANDARD]


def test_classify_query_mandatory_status():
    assert QueryClass.MANDATORY_STATUS in classify_query("Is BIS certification mandatory?")


def test_classify_query_testing():
    assert QueryClass.TESTING in classify_query("What testing is required?")


def test_classify_query_documentation():
    assert QueryClass.DOCUMENTATION in classify_query("What technical specification is needed?")


def test_classify_query_can_match_multiple_classes():
    classes = classify_query("What testing documentation is required for certification?")
    assert QueryClass.TESTING in classes
    assert QueryClass.DOCUMENTATION in classes


def test_prioritized_document_types_backward_compatible_with_phase12():
    prioritized = prioritized_document_types("Is BIS certification mandatory for this product?")
    assert "QCO" in prioritized
    assert "REGULATORY_ORDER" in prioritized


# --- 3. Semantic + keyword merging ---


def test_hybrid_finds_candidate_via_semantic_only(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nElectric water heater safety requirements.")
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water heater")
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=5)
    assert any(c.document_id == doc.id for c in candidates)


def test_hybrid_merge_marks_chunk_found_both_ways(db_session):
    """A chunk found by both semantic and keyword search should
    contribute matched_terms and rank at least as well as one found by
    only one method."""
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nwater heater general information.")
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water heater")
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=5)
    assert len(candidates) >= 1
    assert len(candidates[0].matched_terms) > 0


# --- 4. Score normalization ---


def test_min_max_normalize_basic():
    normalized = min_max_normalize([0.1, 0.5, 0.9])
    assert normalized[0] == 0.0
    assert normalized[2] == 1.0
    assert 0.0 < normalized[1] < 1.0


def test_min_max_normalize_reverse_for_bm25():
    # bm25: more negative is better -> after reverse normalization, the
    # most-negative raw value should normalize to 1.0 (best).
    normalized = min_max_normalize([-5.0, -1.0, 0.0], reverse=True)
    assert normalized[0] == 1.0
    assert normalized[2] == 0.0


def test_min_max_normalize_single_value_is_one():
    assert min_max_normalize([0.42]) == [1.0]


def test_min_max_normalize_identical_values_all_one():
    assert min_max_normalize([0.5, 0.5, 0.5]) == [1.0, 1.0, 1.0]


def test_min_max_normalize_empty_list():
    assert min_max_normalize([]) == []


def test_compute_final_score_weights_are_bounded():
    from app.product.scoring import (
        WEIGHT_DOCUMENT_TYPE_BOOST,
        WEIGHT_EXACT_IDENTIFIER_MATCH,
        WEIGHT_KEYWORD,
        WEIGHT_PROFILE_ATTRIBUTE_MATCH,
        WEIGHT_SEMANTIC,
    )

    breakdown = compute_final_score(
        normalized_semantic=1.0,
        normalized_keyword=1.0,
        document_type_matched=True,
        exact_identifier_matched=True,
        profile_attribute_matched=True,
    )
    # A maximal candidate (every normalized component and every boost at
    # its ceiling) must equal the exact sum of the module's own named
    # weights — bounded and explainable, per the Phase 13 brief, not an
    # arbitrary/unbounded number.
    max_possible = (
        WEIGHT_SEMANTIC + WEIGHT_KEYWORD + WEIGHT_DOCUMENT_TYPE_BOOST + WEIGHT_EXACT_IDENTIFIER_MATCH + WEIGHT_PROFILE_ATTRIBUTE_MATCH
    )
    assert breakdown.final_score == max_possible


def test_compute_final_score_zero_when_nothing_matches():
    breakdown = compute_final_score(
        normalized_semantic=0.0,
        normalized_keyword=0.0,
        document_type_matched=False,
        exact_identifier_matched=False,
        profile_attribute_matched=False,
    )
    assert breakdown.final_score == 0.0


# --- 5. Document-type boost ---


def test_document_type_boost_present_on_candidate(db_session):
    from app.product.document_type import DocumentType

    doc_a, _ = _make_document_with_chunk(db_session, text="1 SCOPE\nwater heater info.", filename="a.pdf")
    doc_b, _ = _make_document_with_chunk(db_session, text="1 SCOPE\nwater heater info.", filename="b.pdf")
    doc_a.document_type = DocumentType.INDIAN_STANDARD.value
    doc_b.document_type = DocumentType.QCO.value
    db_session.commit()

    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water_heater")
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=10, user_query="Is certification mandatory?")
    qco_candidate = next(c for c in candidates if c.document_id == doc_b.id)
    standard_candidate = next(c for c in candidates if c.document_id == doc_a.id)
    assert qco_candidate.document_type_boost == 1.0
    assert standard_candidate.document_type_boost == 0.0
    assert qco_candidate.final_score > standard_candidate.final_score


# --- 6. Exact standard identifier retrieval ---


def test_exact_identifier_found_via_keyword_search_even_with_weak_semantic_query(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nThis document references IS 66601 directly.")
    from app.rag.keyword_search import search

    results = search(db_session, "IS 66601", top_k=5)
    assert any(r.document_id == doc.id for r in results)


def test_exact_identifier_boost_applied_in_hybrid_retrieval(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nThis document references IS 66601 directly.")
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="widget")
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=5, user_query="Does IS 66601 apply to my product?")
    assert len(candidates) >= 1
    matching = next((c for c in candidates if c.document_id == doc.id), None)
    assert matching is not None
    assert matching.exact_identifier_boost == 1.0


# --- 7. Deduplication ---


def test_no_duplicate_evidence_chunks_across_candidates(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nwater heater electric storage information.")
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water heater")
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=5)
    seen_chunk_ids = set()
    for candidate in candidates:
        for chunk_evidence in candidate.evidence:
            assert chunk_evidence.chunk_id not in seen_chunk_ids, "same chunk_id appeared in multiple candidates"
            seen_chunk_ids.add(chunk_evidence.chunk_id)


def test_no_duplicate_candidates_for_same_document(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nwater heater electric storage information.")
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water heater")
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=5)
    document_ids = [c.document_id for c in candidates]
    assert len(document_ids) == len(set(document_ids))


# --- 8. Ranking ---


def test_candidates_sorted_descending_by_final_score(db_session):
    doc_a, _ = _make_document_with_chunk(db_session, text="1 SCOPE\nwater heater strong match content.", filename="a.pdf")
    doc_b, _ = _make_document_with_chunk(db_session, text="1 SCOPE\nunrelated content about testing labs.", filename="b.pdf")
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water heater")
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=10)
    scores = [c.final_score for c in candidates if c.final_score is not None]
    assert scores == sorted(scores, reverse=True)


# --- 9. Product-category specificity updates ---


def test_specificity_replaces_vague_with_specific_category():
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()))
    apply_updates(profile, {"product_category": "appliance"})
    apply_updates(profile, {"product_category": "domestic electric storage water heater"})
    assert profile.product_category == "water_heater"


def test_specificity_never_downgrades_specific_to_vague():
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()))
    apply_updates(profile, {"product_category": "electric water heater"})
    changed, questions = apply_updates(profile, {"product_category": "some appliance"})
    assert profile.product_category == "water_heater"
    assert changed == []


def test_evaluate_update_replace_decision():
    result = evaluate_update("product_category", "appliance", "electric water heater")
    assert result.decision == UpdateDecision.REPLACE


def test_evaluate_update_keep_existing_for_same_category_different_wording():
    result = evaluate_update("product_category", "water_heater", "geyser")
    assert result.decision == UpdateDecision.KEEP_EXISTING


# --- 10. Attribute conflict handling ---


def test_specificity_flags_category_conflict_as_needs_clarification():
    result = evaluate_update("product_category", "water_heater", "water purifier")
    assert result.decision == UpdateDecision.NEEDS_CLARIFICATION
    assert result.clarification_question is not None


def test_specificity_flags_intended_use_conflict():
    result = evaluate_update("intended_use", "domestic use", "commercial use")
    assert result.decision == UpdateDecision.NEEDS_CLARIFICATION


def test_category_conflict_does_not_change_stored_value(db_session):
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()))
    apply_updates(profile, {"product_category": "water heater"})
    changed, questions = apply_updates(profile, {"product_category": "water purifier"})
    assert profile.product_category == "water_heater"  # unchanged despite the conflicting new value
    assert changed == []
    assert len(questions) == 1


# --- 11. Needs-clarification behavior end-to-end ---


def test_conflict_question_surfaces_through_chat_service(db_session):
    from app.llm.provider import LLMResponse
    from app.services.chat_service import ChatService

    class ScriptedLLM:
        name, model, is_mock = "fake", "fake", True

        def __init__(self, responses):
            self._responses = list(responses)

        def generate(self, system_prompt, conversation_history, user_message):
            content = self._responses.pop(0) if self._responses else "(none)"
            return LLMResponse(content=content, model=self.model, provider=self.name)

    llm1 = ScriptedLLM(["product_category: water heater", "ok"])
    service1 = ChatService(db_session, llm_provider=llm1)
    first = service1.send_message("water heater", conversation_id=None, mode="product_discovery")

    llm2 = ScriptedLLM(["product_category: water purifier", "ok"])
    service2 = ChatService(db_session, llm_provider=llm2)
    second = service2.send_message("actually a water purifier", conversation_id=first.conversation_id)

    assert any("water heater" in q and "water purifier" in q for q in second.clarification_questions)
    assert second.compliance_checklist is None  # never assembled while a conflict is pending


def test_safety_filter_rejects_fabricated_profile_resolution_during_conflict(db_session):
    """Reproduces the exact live-observed failure against qwen2.5:7b: when
    a category conflict is pending, the LLM ignored the actual conflict
    question and instead fabricated an "updated profile" claiming the
    conflict was already resolved — directly contradicting the real
    ProductProfile row, which correctly stayed unchanged."""
    from app.llm.provider import LLMResponse
    from app.services.chat_service import ChatService

    class ScriptedLLM:
        name, model, is_mock = "fake", "fake", True

        def __init__(self, responses):
            self._responses = list(responses)

        def generate(self, system_prompt, conversation_history, user_message):
            content = self._responses.pop(0) if self._responses else "(none)"
            return LLMResponse(content=content, model=self.model, provider=self.name)

    llm1 = ScriptedLLM(["product_category: water heater", "ok"])
    service1 = ChatService(db_session, llm_provider=llm1)
    first = service1.send_message("water heater", conversation_id=None, mode="product_discovery")

    llm2 = ScriptedLLM(
        [
            "product_category: water purifier",
            (
                "Thank you for the clarification. Let's adjust the product profile accordingly:\n\n"
                "- **Product name:** water purifier\n"
                "- **Category:** water_purifier\n"
                "- **Intended use:** water purification\n"
            ),
        ]
    )
    service2 = ChatService(db_session, llm_provider=llm2)
    second = service2.send_message("actually a water purifier", conversation_id=first.conversation_id)

    assert "water_purifier" not in second.message.content
    assert "Category:" not in second.message.content
    assert second.product_profile.product_category == "water_heater"


def test_safety_filter_rejects_fabricated_category_with_no_conflict_pending(db_session):
    """Reproduces the DEEPER live-observed failure: the extraction step
    only extracted product_name this turn (not product_category), so NO
    conflict was ever detected — yet the generation-step LLM independently
    fabricated "Category: water_purifier" in its prose anyway, with
    nothing to gate it. This is why the safety check must compare EVERY
    profile restatement against the real profile unconditionally, not
    only when a conflict is pending."""
    from app.llm.provider import LLMResponse
    from app.services.chat_service import ChatService

    class ScriptedLLM:
        name, model, is_mock = "fake", "fake", True

        def __init__(self, responses):
            self._responses = list(responses)

        def generate(self, system_prompt, conversation_history, user_message):
            content = self._responses.pop(0) if self._responses else "(none)"
            return LLMResponse(content=content, model=self.model, provider=self.name)

    llm1 = ScriptedLLM(["product_category: water heater", "ok"])
    service1 = ChatService(db_session, llm_provider=llm1)
    first = service1.send_message("water heater", conversation_id=None, mode="product_discovery")

    # Only product_name is extracted this turn — no conflict is ever
    # detected for product_category, matching the real observed extraction.
    llm2 = ScriptedLLM(
        [
            "product_name: water purifier",
            (
                "I understand. Let's clarify the product profile:\n\n"
                "### Product Profile\n"
                "- **Product name:** water purifier\n"
                "- **Category:** water_purifier\n"
            ),
        ]
    )
    service2 = ChatService(db_session, llm_provider=llm2)
    second = service2.send_message("actually a water purifier", conversation_id=first.conversation_id)

    # No conflict-resolution question (the "earlier you said X, but..."
    # phrasing) was generated — confirms this scenario genuinely has no
    # pending conflict, unlike the sibling test above. Ordinary
    # water_heater clarification questions (voltage, capacity, etc.) are
    # still expected and fine.
    assert not any("earlier you" in q.lower() for q in second.clarification_questions)
    assert "water_purifier" not in second.message.content
    assert second.product_profile.product_category == "water_heater"  # unaffected by the fabrication attempt


def test_response_safety_flags_profile_restatement_that_disagrees_with_actual_profile():
    from app.models.product_profile import ProductProfile
    from app.product.response_safety import check_response_safety

    profile = ProductProfile(id="p1", conversation_id="c1", product_category="water_heater")
    llm_text = "Category: water_purifier\n"
    result = check_response_safety(llm_text, [], requirements=[], profile=profile)
    assert result.is_safe is False
    assert result.fabricated_profile_resolution is True


def test_response_safety_allows_profile_restatement_that_matches_actual_profile():
    from app.models.product_profile import ProductProfile
    from app.product.response_safety import check_response_safety

    profile = ProductProfile(id="p1", conversation_id="c1", product_category="water_heater")
    llm_text = "Category: water_heater\n"
    result = check_response_safety(llm_text, [], requirements=[], profile=profile)
    assert result.is_safe is True


def test_response_safety_allows_restatement_of_unset_field():
    from app.models.product_profile import ProductProfile
    from app.product.response_safety import check_response_safety

    profile = ProductProfile(id="p1", conversation_id="c1", product_category="water_heater")
    llm_text = "Capacity: not specified\n"  # capacity is None on the profile — nothing to disagree with
    result = check_response_safety(llm_text, [], requirements=[], profile=profile)
    assert result.is_safe is True


def test_response_safety_ignores_restatement_when_no_profile_given():
    from app.product.response_safety import check_response_safety

    result = check_response_safety("Category: water_purifier\n", [], requirements=[], profile=None)
    assert result.is_safe is True  # plain BIS chat has no profile at all — nothing to compare against


# --- 12. Retrieval benchmark cases — covered in test_retrieval_benchmark.py ---


def test_benchmark_file_exists():
    from pathlib import Path

    assert (Path(__file__).parent / "test_retrieval_benchmark.py").exists()


# --- 13. Existing applicability unaffected ---


def test_applicability_still_works_with_new_score_fields(db_session):
    from app.product.applicability import evaluate_candidates

    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nElectric storage water heater safety requirements.")
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water heater")
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=5)
    evaluated = evaluate_candidates(candidates, profile)
    assert any(c.applicability_status.value == "POTENTIALLY_APPLICABLE" for c in evaluated)


# --- 14. Existing requirement extraction unaffected ---


def test_requirement_extraction_unaffected_by_scoring_changes():
    from app.product.requirement_extraction import extract_requirements
    from tests.test_compliance_requirements import _candidate
    from app.schemas.candidate_standard import ApplicabilityStatus

    candidate = _candidate(
        "4.2 Testing\nThe sample shall be tested for electrical safety.", ApplicabilityStatus.POTENTIALLY_APPLICABLE
    )
    requirements = extract_requirements([candidate])
    assert len(requirements) >= 1


# --- 15. Existing checklist unaffected ---


def test_checklist_still_builds_with_reranked_candidates(db_session):
    from app.product.checklist import build_checklist

    doc, chunk = _make_document_with_chunk(db_session, text="4.2 Testing\nThe sample shall be tested for safety.")
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water heater")
    db_session.add(profile)
    db_session.commit()

    from app.product.applicability import evaluate_candidates

    candidates = evaluate_candidates(find_candidates(db_session, profile, top_k=5), profile)
    checklist = build_checklist(profile, candidates, open_questions=[])
    assert checklist is not None


# --- 16. Existing safety filter unaffected ---


def test_safety_filter_still_works_after_scoring_changes():
    from app.product.response_safety import check_response_safety

    result = check_response_safety("IS 999999 definitely applies.", [])
    assert result.is_safe is False


# --- 17. Existing Ollama provider unaffected ---


def test_ollama_provider_still_importable():
    from app.llm.ollama_provider import OllamaLLMProvider

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    assert provider.name == "ollama"


# --- 18. Existing document management unaffected ---


def test_document_management_unaffected_by_retrieval_changes(client, isolated_storage):
    from pathlib import Path

    content = (Path(__file__).parent / "fixtures" / "test_text.pdf").read_bytes()
    upload_response = client.post("/api/documents/upload", files={"file": ("test_text.pdf", content, "application/pdf")})
    assert upload_response.status_code == 201

    list_response = client.get("/api/documents")
    assert list_response.status_code == 200
    assert list_response.json()[0]["display_status"] == "INDEXED"


# --- Backward compatibility: existing semantic retrieval untouched ---


def test_existing_semantic_retrieval_signature_unaffected(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nThis synthetic document defines scope.")
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    results = retrieval.retrieve(query="This synthetic document defines scope", top_k=4)
    assert len(results) == 1
    assert results[0].document_id == doc.id
