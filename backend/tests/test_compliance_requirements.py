"""
Phase 11 tests — evidence-based compliance plan & checklist engine.

Uses hand-written LLM test doubles exclusively (matching test_product_discovery.py's
conventions), never a real external API call. Reuses ScriptedFakeLLM and
_make_document_with_chunk from tests/test_product_discovery.py rather than
duplicating them.

All evidence used here is the SYNTHETIC TEST FIXTURES from
tests/fixtures/generate_test_pdfs.py — never real BIS documents. This
suite proves the requirement-extraction/checklist PIPELINE works; it makes
no claim about real BIS compliance coverage, mandatory status, or
certification requirements.
"""

import uuid

from app.models.product_profile import ProductProfile
from app.product.applicability import evaluate_candidates
from app.product.checklist import build_checklist
from app.product.hybrid_retrieval import find_candidates
from app.product.requirement_extraction import extract_requirements
from app.product.response_safety import build_fallback_response, check_response_safety
from app.rag.retrieval import RetrievalService
from app.schemas.candidate_standard import ApplicabilityStatus, CandidateStandard
from app.schemas.compliance import RegulatoryStatus, RequirementCategory, RequirementStatus
from app.schemas.retrieval import RetrievedChunk
from app.services.chat_service import ChatService
from tests.test_embeddings import FakeEmbeddingProvider
from tests.test_product_discovery import ScriptedFakeLLM, _make_document_with_chunk


def _candidate(text: str, status: ApplicabilityStatus, document_name: str = "test_text.pdf") -> CandidateStandard:
    return CandidateStandard(
        document_id="d1",
        standard_id=None,
        document_name=document_name,
        relevance_score=0.85,
        matched_terms=[],
        evidence=[
            RetrievedChunk(
                chunk_id="c1", document_id="d1", document_name=document_name, page_number=1, section="4.2",
                text=text, similarity_score=0.85,
            )
        ],
        applicability_status=status,
        applicability_reason="test",
    )


# --- 1. Requirement extraction from evidence ---


def test_requirement_extracted_from_evidence_with_obligation_language():
    candidate = _candidate(
        "4.2 Testing\nThe sample shall be tested in accordance with the specified method.",
        ApplicabilityStatus.POTENTIALLY_APPLICABLE,
    )
    requirements = extract_requirements([candidate])
    assert len(requirements) >= 1
    assert requirements[0].category == RequirementCategory.TESTING


def test_no_requirement_extracted_from_plain_scope_text_without_obligation_language():
    candidate = _candidate(
        "1 SCOPE\nThis document exists only to test the ingestion pipeline.",
        ApplicabilityStatus.POTENTIALLY_APPLICABLE,
    )
    requirements = extract_requirements([candidate])
    assert requirements == []


# --- 2. Evidence reference preservation ---


def test_extracted_requirement_preserves_evidence_reference():
    candidate = _candidate(
        "4.2 Testing\nThe sample shall be tested before release.", ApplicabilityStatus.POTENTIALLY_APPLICABLE
    )
    requirements = extract_requirements([candidate])
    assert len(requirements) == 1
    req = requirements[0]
    assert req.evidence[0].chunk_id == "c1"
    assert req.evidence[0].document_id == "d1"
    assert req.evidence[0].page_number == 1
    assert req.evidence[0].section == "4.2"
    assert req.source_document_ids == ["d1"]


# --- 3. Testing requirement extraction ---


def test_testing_keyword_produces_testing_category():
    candidate = _candidate(
        "5.1 Method\nEach unit must be tested for electrical safety before dispatch.",
        ApplicabilityStatus.POTENTIALLY_APPLICABLE,
    )
    requirements = extract_requirements([candidate])
    assert any(r.category == RequirementCategory.TESTING for r in requirements)


# --- 4. Documentation requirement extraction ---


def test_documentation_keyword_produces_documentation_category():
    candidate = _candidate(
        "6.1 Records\nA test report and technical specification must be maintained for each batch.",
        ApplicabilityStatus.POTENTIALLY_APPLICABLE,
    )
    requirements = extract_requirements([candidate])
    assert any(r.category == RequirementCategory.DOCUMENTATION for r in requirements)


# --- 5. Certification requirement separation ---


def test_certification_category_kept_separate_from_testing():
    candidate = _candidate(
        "7 Certification\nA valid certificate is required for market entry.",
        ApplicabilityStatus.POTENTIALLY_APPLICABLE,
    )
    requirements = extract_requirements([candidate])
    categories = {r.category for r in requirements}
    assert RequirementCategory.CERTIFICATION in categories
    assert RequirementCategory.TESTING not in categories


# --- 6. Mandatory-status uncertainty ---


def test_regulatory_status_always_not_determined():
    """No rule anywhere can produce MANDATORY_CONFIRMED in this phase —
    this project has no QCO/regulatory metadata to justify it."""
    candidate = _candidate(
        "7 Certification\nA valid certificate is mandatory before sale.",  # even evidence saying "mandatory"
        ApplicabilityStatus.APPLICABLE,
    )
    requirements = extract_requirements([candidate])
    assert all(r.regulatory_status == RegulatoryStatus.NOT_DETERMINED for r in requirements)


# --- 7. NEEDS_CLARIFICATION when evidence is insufficient ---


def test_needs_clarification_candidates_produce_no_requirements():
    """A candidate still at NEEDS_CLARIFICATION has not been confirmed
    relevant yet — extracting requirements from it would be requirement
    generation ahead of applicability."""
    candidate = _candidate(
        "4.2 Testing\nThe sample shall be tested.", ApplicabilityStatus.NEEDS_CLARIFICATION
    )
    requirements = extract_requirements([candidate])
    assert requirements == []


def test_not_applicable_candidates_produce_no_requirements():
    candidate = _candidate(
        "4.2 Testing\nThe sample shall be tested.", ApplicabilityStatus.NOT_APPLICABLE
    )
    requirements = extract_requirements([candidate])
    assert requirements == []


# --- 8. No unsupported requirement generation ---


def test_empty_candidates_produce_empty_checklist():
    requirements = extract_requirements([])
    assert requirements == []


def test_requirement_status_matches_candidate_applicability():
    confirmed_candidate = _candidate(
        "4.2 Testing\nThe sample shall be tested.", ApplicabilityStatus.APPLICABLE
    )
    potential_candidate = _candidate(
        "4.2 Testing\nThe sample shall be tested.", ApplicabilityStatus.POTENTIALLY_APPLICABLE, document_name="b.pdf"
    )
    confirmed_reqs = extract_requirements([confirmed_candidate])
    potential_reqs = extract_requirements([potential_candidate])
    assert confirmed_reqs[0].status == RequirementStatus.CONFIRMED
    assert potential_reqs[0].status == RequirementStatus.POTENTIALLY_APPLICABLE


# --- 9. LLM fabricated requirement rejection (rephrase safety) ---


def test_rephrase_ignored_when_llm_adds_new_claims():
    from app.product.requirement_extraction import rephrase_requirement_text

    class FabricatingLLM:
        name, model, is_mock = "fake", "fake", True

        def generate(self, system_prompt, conversation_history, user_message):
            from app.llm.provider import LLMResponse

            return LLMResponse(
                content="This is mandatory and IS 99999999 requires annual third-party certification renewal.",
                model=self.model,
                provider=self.name,
            )

    result = rephrase_requirement_text(FabricatingLLM(), "shall be tested")
    # Much longer than the tiny original -> rejected, falls back to raw evidence text.
    assert result is None


def test_rephrase_accepted_when_llm_output_is_a_reasonable_simplification():
    class SimplifyingLLM:
        name, model, is_mock = "fake", "fake", True

        def generate(self, system_prompt, conversation_history, user_message):
            from app.llm.provider import LLMResponse

            return LLMResponse(content="The product must be tested before sale.", model=self.model, provider=self.name)

    from app.product.requirement_extraction import rephrase_requirement_text

    result = rephrase_requirement_text(SimplifyingLLM(), "4.2 shall be tested before sale")
    assert result == "The product must be tested before sale."


# --- 10. LLM fabricated IS-number rejection (Phase 10, still enforced) ---


def test_safety_filter_still_rejects_fabricated_is_numbers():
    candidates = [_candidate("1 SCOPE\nSynthetic content only.", ApplicabilityStatus.NEEDS_CLARIFICATION)]
    result = check_response_safety("IS 55555 definitely applies to this product.", candidates)
    assert result.is_safe is False
    assert len(result.fabricated_standard_numbers) >= 1


# --- 11. LLM fabricated mandatory-status rejection (Phase 11) ---


def test_safety_filter_rejects_mandatory_language():
    candidates = [_candidate("4.2 Testing\nThe sample shall be tested.", ApplicabilityStatus.POTENTIALLY_APPLICABLE)]
    result = check_response_safety(
        "This certification is mandatory and legally required for your product.", candidates
    )
    assert result.is_safe is False
    assert result.fabricated_mandatory_claim is True


def test_safety_filter_accepts_not_determined_language():
    candidates = [_candidate("4.2 Testing\nThe sample shall be tested.", ApplicabilityStatus.POTENTIALLY_APPLICABLE)]
    result = check_response_safety(
        "Mandatory status has not been determined for this requirement.", candidates
    )
    assert result.is_safe is True


def test_fallback_response_never_claims_mandatory_status():
    candidate = _candidate("4.2 Testing\nThe sample shall be tested.", ApplicabilityStatus.POTENTIALLY_APPLICABLE)
    requirements = extract_requirements([candidate])
    fallback = build_fallback_response([], [candidate], requirements=requirements)
    assert "mandatory" in fallback.lower()  # only in the honest "could not be determined" sentence
    assert "could not be determined" in fallback.lower()
    result = check_response_safety(fallback, [candidate], requirements)
    assert result.is_safe is True  # the fallback itself must always pass its own safety check


# --- Fabricated checklist items (live-testing-discovered case) ---
#
# Reproduces the exact live-observed failure against qwen2.5:7b: two
# candidates stayed NEEDS_CLARIFICATION (so extract_requirements()
# correctly produced zero items), yet the model invented a "Requirements
# Checklist" section naming specific requirements from its own reading of
# the evidence rather than the actual (empty) structured list.


def test_safety_filter_rejects_checklist_items_when_none_were_extracted():
    llm_text = (
        "### Requirements Checklist\n"
        "- Electrical Safety Testing: Each sample shall be tested for electrical safety.\n"
        "- Marking Requirements: Every unit shall be marked with rated voltage.\n"
    )
    result = check_response_safety(llm_text, [], requirements=[])
    assert result.is_safe is False
    assert result.fabricated_checklist_items is True


def test_safety_filter_accepts_checklist_items_when_requirements_exist():
    candidate = _candidate("4.2 Testing\nThe sample shall be tested.", ApplicabilityStatus.POTENTIALLY_APPLICABLE)
    requirements = extract_requirements([candidate])
    llm_text = "- Testing: the sample shall be tested for electrical safety."
    result = check_response_safety(llm_text, [candidate], requirements=requirements)
    assert result.is_safe is True


def test_safety_filter_does_not_flag_plain_prose_mention_of_testing():
    """A bare mention of a category word in ordinary prose (not a
    list/heading construct) must not be treated as a fabricated checklist
    item — only list-marker-style presentation triggers the check."""
    llm_text = "The retrieved document discusses testing procedures in general terms."
    result = check_response_safety(llm_text, [], requirements=[])
    assert result.fabricated_checklist_items is False


def test_discovery_turn_substitutes_fallback_when_llm_invents_checklist_items(db_session):
    """End-to-end reproduction of the live-observed fabrication: two
    NEEDS_CLARIFICATION candidates, LLM invents a checklist anyway."""
    doc, chunk = _make_document_with_chunk(
        db_session, text="1 SCOPE\nElectric storage water heater safety requirements."
    )
    llm = ScriptedFakeLLM(
        responses=[
            "product_category: household appliances\nproduct_type: storage-type\nelectrical_characteristics: 230V\n"
            "capacity: 15 litres\nintended_use: domestic\ntechnology: immersion\nmaterials: copper\n"
            "target_market: India\nmanufacturing_location: India",
            (
                "### Requirements Checklist\n"
                "- Electrical Safety Testing: shall be tested before dispatch.\n"
                "- Marking Requirements: shall be marked with rated voltage.\n"
            ),
        ]
    )
    service = ChatService(db_session, llm_provider=llm)

    response = service.send_message(
        "storage water heater 230V 15 litres domestic immersion copper, India, made in India",
        conversation_id=None,
        mode="product_discovery",
    )

    assert "Electrical Safety Testing" not in response.message.content
    assert "Marking Requirements" not in response.message.content
    # The real structured checklist must also genuinely be empty here,
    # confirming the rejection was correct and not a false positive.
    assert response.compliance_checklist is not None
    assert response.compliance_checklist.items == []


# --- 12. Checklist generation ---


def test_build_checklist_produces_items_from_applicable_candidates(db_session):
    profile = ProductProfile(
        id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water heater"
    )
    candidate = _candidate(
        "4.2 Testing\nElectric water heater sample shall be tested for electrical safety.",
        ApplicabilityStatus.POTENTIALLY_APPLICABLE,
    )
    checklist = build_checklist(profile, [candidate], open_questions=[])
    assert len(checklist.items) >= 1
    assert checklist.candidate_standards == [candidate]
    assert checklist.product_profile.product_category == "water heater"


def test_build_checklist_empty_when_no_candidates(db_session):
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="widget")
    checklist = build_checklist(profile, [], open_questions=["What is it?"])
    assert checklist.items == []
    assert checklist.open_questions == ["What is it?"]


# --- 13. Checklist evidence traceability ---


def test_checklist_items_are_traceable_to_evidence(db_session):
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water heater")
    candidate = _candidate(
        "4.2 Testing\nElectric water heater sample shall be tested.", ApplicabilityStatus.APPLICABLE
    )
    checklist = build_checklist(profile, [candidate], open_questions=[])
    for item in checklist.items:
        assert len(item.evidence) > 0
        assert item.evidence[0].chunk_id == "c1"
        assert item.source_document_ids == ["d1"]


# --- 14. ProductProfile integration (end-to-end via ChatService) ---


def test_checklist_appears_in_chat_response_once_profile_is_sufficient(db_session):
    doc, chunk = _make_document_with_chunk(
        db_session, text="4.2 Testing\nElectric water heater sample shall be tested for safety."
    )
    llm = ScriptedFakeLLM(
        responses=[
            "product_category: water_heater\nproduct_type: storage\nelectrical_characteristics: 230V, 2000W\n"
            "capacity: 15 litres\nintended_use: domestic\ntechnology: immersion element\nmaterials: copper",
            "Here is what I found.",
        ]
    )
    service = ChatService(db_session, llm_provider=llm)

    response = service.send_message(
        "storage water heater, 230V 2000W, 15 litres, domestic, immersion element, copper",
        conversation_id=None,
        mode="product_discovery",
    )

    assert response.compliance_checklist is not None
    assert response.compliance_checklist.product_profile.product_category == "water_heater"


def test_checklist_absent_when_profile_still_needs_clarification(db_session):
    llm = ScriptedFakeLLM(responses=["product_category: water_heater", "ok"])
    service = ChatService(db_session, llm_provider=llm)

    response = service.send_message("water heater", conversation_id=None, mode="product_discovery")

    assert response.compliance_checklist is None
    assert len(response.clarification_questions) > 0


# --- 15. Existing candidate-standard behavior unaffected ---


def test_candidate_standard_applicability_unaffected_by_checklist_addition(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nElectric storage water heater safety requirements.")
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water heater")
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=4)
    evaluated = evaluate_candidates(candidates, profile)

    assert any(c.applicability_status == ApplicabilityStatus.POTENTIALLY_APPLICABLE for c in evaluated)


# --- 16. Existing citations unaffected ---


def test_citations_unchanged_when_checklist_is_present(db_session):
    doc, chunk = _make_document_with_chunk(
        db_session, text="4.2 Testing\nElectric water heater sample shall be tested for safety."
    )
    llm = ScriptedFakeLLM(
        responses=[
            "product_category: water_heater\nproduct_type: storage\nelectrical_characteristics: 230V\n"
            "capacity: 15 litres\nintended_use: domestic\ntechnology: immersion\nmaterials: copper",
            "answer",
        ]
    )
    service = ChatService(db_session, llm_provider=llm)

    response = service.send_message(
        "storage water heater 230V 15 litres domestic immersion copper",
        conversation_id=None,
        mode="product_discovery",
    )

    for citation in response.message.citations:
        assert citation.document_id == doc.id
        assert citation.chunk_id == chunk.id


# --- 17. Existing Ollama integration unaffected ---


def test_ollama_provider_still_importable_and_unaffected():
    from app.llm.ollama_provider import OllamaLLMProvider

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    assert provider.name == "ollama"


# --- 18. Existing document management unaffected ---


def test_document_management_unaffected_by_compliance_engine(client, isolated_storage):
    from pathlib import Path

    fixture_path = Path(__file__).parent / "fixtures" / "test_text.pdf"
    content = fixture_path.read_bytes()

    upload_response = client.post("/api/documents/upload", files={"file": ("test_text.pdf", content, "application/pdf")})
    assert upload_response.status_code == 201

    list_response = client.get("/api/documents")
    assert list_response.status_code == 200
    assert list_response.json()[0]["display_status"] == "INDEXED"


# --- Backward compatibility: plain chat unaffected ---


def test_plain_chat_has_no_compliance_checklist_field_populated(db_session):
    llm = ScriptedFakeLLM(responses=["plain answer"])
    service = ChatService(
        db_session, retrieval_service=RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider()), llm_provider=llm
    )

    response = service.send_message("What is the scope?", conversation_id=None)

    assert response.compliance_checklist is None
