"""
Phase 10 tests — product discovery + compliance intelligence engine.

Uses hand-written LLM test doubles exclusively (matching test_chat_rag.py's
conventions), never a real external API call. Since a discovery turn calls
LLMProvider.generate() twice (once for profile extraction, once for the
final natural-language response), ScriptedFakeLLM below returns responses
in a fixed sequence so tests can control exactly what each call returns.

All evidence used here is the SYNTHETIC TEST FIXTURES from
tests/fixtures/generate_test_pdfs.py — never real BIS documents. This
suite proves the discovery PIPELINE works; it makes no claim about real
BIS compliance coverage.
"""

import uuid

import pytest

from app.llm.provider import LLMResponse
from app.models.document_chunk import DocumentChunk
from app.models.product_profile import ProductProfile
from app.models.standard_document import StandardDocument
from app.product.applicability import determine_applicability, evaluate_candidates
from app.product.clarification import (
    CATEGORY_QUESTIONS,
    has_sufficient_information,
    missing_field_questions,
)
from app.product.hybrid_retrieval import find_candidates
from app.product.profile_extraction import apply_updates, parse_extraction_output
from app.product.response_safety import build_fallback_response, check_response_safety
from app.product.search_terms import derive_search_terms
from app.rag.retrieval import RetrievalService
from app.rag.vector_store import serialize_embedding
from app.schemas.candidate_standard import ApplicabilityStatus, CandidateStandard
from app.schemas.retrieval import RetrievedChunk
from app.services.chat_service import ChatService
from tests.test_embeddings import FakeEmbeddingProvider


class ScriptedFakeLLM:
    """Returns responses from a fixed queue, one per generate() call, in
    order. Used because a discovery turn calls generate() twice (extraction,
    then the final response) — a plain echo fake can't represent that."""

    name = "fake"
    model = "fake-model"
    is_mock = True

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = []

    def generate(self, system_prompt, conversation_history, user_message):
        self.calls.append(
            {"system_prompt": system_prompt, "conversation_history": conversation_history, "user_message": user_message}
        )
        content = self._responses.pop(0) if self._responses else "(none)"
        return LLMResponse(content=content, model=self.model, provider=self.name)


def _make_document_with_chunk(db_session, text, standard_id=None, filename="synthetic_test.pdf"):
    doc = StandardDocument(
        id=str(uuid.uuid4()),
        standard_id=standard_id,
        original_filename=filename,
        file_hash=f"hash-{uuid.uuid4()}",
        mime_type="application/pdf",
        size_bytes=100,
        storage_path="/tmp/fake.pdf",
        status="completed",
        source_type="test",
    )
    db_session.add(doc)
    db_session.commit()

    provider = FakeEmbeddingProvider()
    vector = provider.embed_text(f"passage: {text}")
    chunk = DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        document_page_id=1,
        page_number=1,
        chunk_index=0,
        text=text,
        section="1",
        embedding_json=serialize_embedding(vector),
        embedding_model=provider.model_name,
        embedding_dimension=provider.dimension,
    )
    db_session.add(chunk)
    db_session.commit()

    from app.rag.keyword_search import index_chunks

    index_chunks(db_session, doc.id, [(chunk.id, text)])
    return doc, chunk


# --- 1. Vague product description triggers clarification ---


def test_vague_product_description_asks_clarification_questions(db_session):
    llm = ScriptedFakeLLM(
        responses=[
            "product_category: water heater",  # extraction
            "To help identify requirements, I need a few more details.",  # final response
        ]
    )
    service = ChatService(db_session, retrieval_service=RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider()), llm_provider=llm)

    response = service.send_message(
        "I want to launch an electric water heater.", conversation_id=None, mode="product_discovery"
    )

    assert response.product_profile is not None
    assert response.product_profile.product_category == "water_heater" or response.product_profile.product_category == "water heater"
    assert len(response.clarification_questions) > 0


# --- 2. Product attributes extracted into structured profile ---


def test_product_attributes_extracted_into_profile(db_session):
    llm = ScriptedFakeLLM(
        responses=[
            "product_category: water_heater\nproduct_type: storage\nelectrical_characteristics: 230V, 2000W",
            "Got it, thanks.",
        ]
    )
    service = ChatService(db_session, llm_provider=llm)

    response = service.send_message(
        "It's a storage water heater, 230V 2000W.", conversation_id=None, mode="product_discovery"
    )

    assert response.product_profile.product_category == "water_heater"
    assert response.product_profile.product_type == "storage"
    assert response.product_profile.electrical_characteristics == "230V, 2000W"


# --- 3. Already-answered attributes are not re-requested ---


def test_answered_fields_are_not_included_in_next_clarification_batch(db_session):
    llm1 = ScriptedFakeLLM(responses=["product_category: water_heater\nproduct_type: storage", "ok"])
    service1 = ChatService(db_session, llm_provider=llm1)
    first_response = service1.send_message(
        "storage water heater", conversation_id=None, mode="product_discovery"
    )
    conversation_id = first_response.conversation_id

    assert "product_type" not in [q for q in first_response.clarification_questions]  # sanity: field itself not literally asked

    llm2 = ScriptedFakeLLM(responses=["electrical_characteristics: 230V, 2000W", "thanks"])
    service2 = ChatService(db_session, llm_provider=llm2)
    second_response = service2.send_message(
        "230V 2000W", conversation_id=conversation_id, mode="product_discovery"
    )

    # product_type was already known — its question must never reappear.
    assert not any("storage-type or instant" in q for q in second_response.clarification_questions)
    assert second_response.product_profile.product_type == "storage"  # preserved, not overwritten


# --- 4. Missing attributes remain unknown, never guessed ---


def test_unmentioned_fields_remain_none_not_guessed(db_session):
    llm = ScriptedFakeLLM(responses=["product_category: water_heater", "ok"])
    service = ChatService(db_session, llm_provider=llm)

    response = service.send_message("water heater", conversation_id=None, mode="product_discovery")

    assert response.product_profile.capacity is None
    assert response.product_profile.materials is None
    assert response.product_profile.manufacturing_location is None


def test_extraction_ignores_unknown_value_words():
    updates = parse_extraction_output("capacity: unknown\nproduct_category: water_heater\nmaterials: not specified")
    assert updates == {"product_category": "water_heater"}


def test_extraction_rejects_unrecognized_field_names():
    updates = parse_extraction_output("compliance_score: 95\nproduct_category: water_heater\nis_legal: yes")
    assert updates == {"product_category": "water_heater"}
    assert "compliance_score" not in updates
    assert "is_legal" not in updates


# --- 5. Product profile updates across conversation turns ---


def test_profile_persists_and_evolves_across_turns(db_session):
    llm1 = ScriptedFakeLLM(responses=["product_category: water_purifier", "ok"])
    service = ChatService(db_session, llm_provider=llm1)
    first = service.send_message("water purifier", conversation_id=None, mode="product_discovery")

    llm2 = ScriptedFakeLLM(responses=["technology: RO", "ok"])
    service2 = ChatService(db_session, llm_provider=llm2)
    second = service2.send_message("It uses RO technology.", conversation_id=first.conversation_id, mode="product_discovery")

    assert second.product_profile.product_category == "water_purifier"  # from turn 1, preserved
    assert second.product_profile.technology == "RO"  # from turn 2, added


def test_discovery_mode_continues_without_resending_mode_flag(db_session):
    """Once a ProductProfile exists for a conversation, a later message
    stays in discovery mode even if the client omits mode= on that turn."""
    llm1 = ScriptedFakeLLM(responses=["product_category: water_heater", "ok"])
    service = ChatService(db_session, llm_provider=llm1)
    first = service.send_message("water heater", conversation_id=None, mode="product_discovery")

    llm2 = ScriptedFakeLLM(responses=["capacity: 15 litres", "ok"])
    service2 = ChatService(db_session, llm_provider=llm2)
    second = service2.send_message("15 litres", conversation_id=first.conversation_id, mode=None)

    assert second.product_profile is not None
    assert second.product_profile.capacity == "15 litres"


# --- 6. Search terms derived from product attributes ---


def test_search_terms_derived_from_profile_attributes(db_session):
    profile = ProductProfile(
        id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        product_category="water_heater",
        product_type="storage",
        technology="immersion element",
    )
    terms = derive_search_terms(profile)

    assert "water_heater" in terms
    assert "storage" in terms
    assert "immersion element" in terms
    assert "storage water_heater" in terms  # combined term, built only from present fields


def test_search_terms_never_invents_unstated_vocabulary(db_session):
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="widget")
    terms = derive_search_terms(profile)
    assert terms == ["widget"]  # no invented combination since only one field is present


def test_empty_profile_produces_no_search_terms(db_session):
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()))
    assert derive_search_terms(profile) == []


# --- 7. Existing semantic retrieval remains functional ---


def test_existing_semantic_retrieval_unaffected(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nThis synthetic document defines scope.")
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())

    results = retrieval.retrieve(query="This synthetic document defines scope", top_k=4)

    assert len(results) == 1
    assert results[0].document_id == doc.id


# --- 8. Candidate standards are distinct from applicable standards ---


def test_candidates_default_to_needs_clarification_before_applicability_evaluation(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nElectric storage water heater safety requirements.")
    profile = ProductProfile(
        id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water_heater"
    )
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=4)

    assert len(candidates) >= 1
    # find_candidates alone never assigns anything but NEEDS_CLARIFICATION —
    # that determination is applicability.py's job, not retrieval's.
    assert all(c.applicability_status == ApplicabilityStatus.NEEDS_CLARIFICATION for c in candidates)


def test_evidence_mentioning_category_becomes_potentially_applicable(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nElectric storage water heater safety requirements.")
    profile = ProductProfile(
        id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water heater"
    )
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=4)
    evaluated = evaluate_candidates(candidates, profile)

    assert any(c.applicability_status == ApplicabilityStatus.POTENTIALLY_APPLICABLE for c in evaluated)
    # never escalated to APPLICABLE by this engine — no regulatory/QCO evidence exists to justify that.
    assert all(c.applicability_status != ApplicabilityStatus.APPLICABLE for c in evaluated)


def test_no_numeric_compliance_score_exposed():
    candidate = CandidateStandard(
        document_id="d1",
        standard_id=None,
        document_name="doc.pdf",
        relevance_score=0.9,
        matched_terms=["water heater"],
        evidence=[],
        applicability_status=ApplicabilityStatus.NEEDS_CLARIFICATION,
        applicability_reason="test",
    )
    assert not hasattr(candidate, "compliance_score")
    assert not hasattr(candidate, "launch_readiness")


# --- 9. Insufficient evidence produces NEEDS_CLARIFICATION ---


def test_no_product_category_yields_needs_clarification_regardless_of_evidence(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nElectric storage water heater safety requirements.")
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_name="MyProduct")
    db_session.add(profile)
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=4)
    evaluated = evaluate_candidates(candidates, profile)

    assert all(c.applicability_status == ApplicabilityStatus.NEEDS_CLARIFICATION for c in evaluated)


def test_unrelated_evidence_yields_needs_clarification():
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water_purifier")
    candidate = CandidateStandard(
        document_id="d1",
        standard_id=None,
        document_name="unrelated.pdf",
        relevance_score=0.5,
        matched_terms=[],
        evidence=[
            RetrievedChunk(
                chunk_id="c1", document_id="d1", document_name="unrelated.pdf", page_number=1, section=None,
                text="This document is about testing laboratory accreditation only.", similarity_score=0.5,
            )
        ],
        applicability_status=ApplicabilityStatus.NEEDS_CLARIFICATION,
        applicability_reason="",
    )
    result = determine_applicability(candidate, profile)
    assert result.applicability_status == ApplicabilityStatus.NEEDS_CLARIFICATION


# --- 10 & 11. Citations from RetrievedChunk only; LLM cannot create citation metadata ---


def test_discovery_citations_come_from_retrieved_chunks_not_llm(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nElectric storage water heater safety requirements.")
    llm = ScriptedFakeLLM(
        responses=[
            "product_category: water heater",
            "I found some evidence. See SOURCE 7 page 999 for details.",  # LLM tries to fabricate a citation in prose
        ]
    )
    service = ChatService(db_session, llm_provider=llm)

    response = service.send_message("electric water heater", conversation_id=None, mode="product_discovery")

    # Citations must reflect only what was actually retrieved — never the
    # LLM's fabricated "page 999" mentioned in its own prose.
    for citation in response.message.citations:
        assert citation.document_id == doc.id
        assert citation.page_number != 999
        assert citation.chunk_id == chunk.id


def test_llm_cannot_inject_arbitrary_citation_fields(db_session):
    """Even if the LLM's extraction output tries to smuggle a citation-like
    field name, it is dropped by the allow-list, never reaching the
    profile or any citation."""
    updates = parse_extraction_output("document_id: fake-doc\npage_number: 42\nproduct_category: water_heater")
    assert "document_id" not in updates
    assert "page_number" not in updates
    assert updates == {"product_category": "water_heater"}


# --- 12. Existing standard_id filtering still works ---


def test_standard_id_filtering_still_works_in_plain_chat(db_session):
    from datetime import date

    from app.llm.provider import LLMResponse
    from app.models.standard import Standard

    standard = Standard(
        id=str(uuid.uuid4()), code="IS 88881", title="Test", category="Test", description="test",
        status="active", last_amended=date(2024, 1, 1), sector="Test", source_type="demo",
    )
    db_session.add(standard)
    db_session.commit()

    linked_doc, _ = _make_document_with_chunk(db_session, text="1 SCOPE\nLinked content.", standard_id=standard.id, filename="linked.pdf")
    unlinked_doc, _ = _make_document_with_chunk(db_session, text="1 SCOPE\nUnlinked content.", standard_id=None, filename="unlinked.pdf")

    class EchoLLM:
        name, model, is_mock = "fake", "fake", True

        def generate(self, system_prompt, conversation_history, user_message):
            return LLMResponse(content="answer", model=self.model, provider=self.name)

    service = ChatService(db_session, retrieval_service=RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider()), llm_provider=EchoLLM())
    response = service.send_message("scope content", conversation_id=None, standard_id=standard.id)

    cited_ids = {c.document_id for c in response.message.citations}
    assert cited_ids <= {linked_doc.id}
    assert unlinked_doc.id not in cited_ids


# --- 13. Existing Ollama provider still works (unchanged) ---


def test_ollama_provider_unaffected_by_discovery_module_import():
    from app.llm.ollama_provider import OllamaLLMProvider

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    assert provider.name == "ollama"
    assert provider.is_mock is False


# --- 14. Existing chat behavior remains backward compatible ---


def test_plain_chat_without_mode_field_unaffected(db_session):
    llm = ScriptedFakeLLM(responses=["plain answer, no discovery fields"])
    service = ChatService(db_session, retrieval_service=RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider()), llm_provider=llm)

    response = service.send_message("What is the scope?", conversation_id=None)

    assert response.product_profile is None
    assert response.clarification_questions == []
    assert response.candidate_standards == []
    assert len(llm.calls) == 1  # plain chat never runs the extraction call


def test_chat_endpoint_rejects_unsupported_mode(client):
    response = client.post("/api/chat", json={"message": "test", "mode": "not_a_real_mode"})
    assert response.status_code == 422


def test_chat_endpoint_accepts_product_discovery_mode(client):
    response = client.post("/api/chat", json={"message": "water heater", "mode": "product_discovery"})
    # No LLM configured in the test environment -> 503, but the request
    # itself must pass validation (mode is a supported value).
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"


# --- 15. Existing document management remains functional ---


def test_document_management_unaffected_by_product_discovery(client, isolated_storage):
    from pathlib import Path

    fixture_path = Path(__file__).parent / "fixtures" / "test_text.pdf"
    content = fixture_path.read_bytes()

    upload_response = client.post("/api/documents/upload", files={"file": ("test_text.pdf", content, "application/pdf")})
    assert upload_response.status_code == 201

    list_response = client.get("/api/documents")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["display_status"] == "INDEXED"


# --- Clarification framework: reusable across categories ---


def test_clarification_framework_covers_multiple_categories():
    assert "water_heater" in CATEGORY_QUESTIONS
    assert "water_purifier" in CATEGORY_QUESTIONS
    assert CATEGORY_QUESTIONS["water_heater"] != CATEGORY_QUESTIONS["water_purifier"]


def test_has_sufficient_information_true_when_no_questions_remain():
    profile = ProductProfile(
        id=str(uuid.uuid4()),
        conversation_id=str(uuid.uuid4()),
        product_category="water_purifier",
        technology="RO",
        intended_use="domestic",
        electrical_characteristics="230V",
        capacity="10 L/hr",
    )
    assert has_sufficient_information(profile) is True


def test_has_sufficient_information_false_when_questions_remain():
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water_purifier")
    assert has_sufficient_information(profile) is False
    assert len(missing_field_questions(profile)) > 0


# --- Response safety filter ---
#
# Discovered during live verification against the real local model
# (qwen2.5:7b via Ollama): even under an explicit "only discuss the listed
# candidates" system prompt, the model fabricated IS standard numbers and
# an invented applicability status word ("APPLIES") that were never in the
# retrieved evidence. These tests lock in the hard guardrail added in
# response to that finding (app/product/response_safety.py) — prompt
# wording alone is not trusted to prevent this.


def _candidate_with_evidence_text(text: str, document_name: str = "test_text.pdf") -> CandidateStandard:
    return CandidateStandard(
        document_id="d1",
        standard_id=None,
        document_name=document_name,
        relevance_score=0.8,
        matched_terms=[],
        evidence=[
            RetrievedChunk(
                chunk_id="c1", document_id="d1", document_name=document_name, page_number=1, section=None,
                text=text, similarity_score=0.8,
            )
        ],
        applicability_status=ApplicabilityStatus.NEEDS_CLARIFICATION,
        applicability_reason="test",
    )


def test_safety_check_passes_when_llm_only_mentions_evidence_backed_standards():
    candidates = [_candidate_with_evidence_text("This document references IS 302-1 as an example.")]
    result = check_response_safety("The retrieved evidence mentions IS 302-1.", candidates)
    assert result.is_safe is True
    assert result.fabricated_standard_numbers == []


def test_safety_check_rejects_fabricated_standard_number_not_in_evidence():
    """Reproduces the exact live-observed failure: the LLM named IS
    standards that were never in the retrieved evidence."""
    candidates = [_candidate_with_evidence_text("1 SCOPE\nThis synthetic document exists only to test the pipeline.")]
    llm_text = (
        "Based on your product, IS 15919:2013 - Electric Water Heaters likely applies, "
        "along with IS 13202:2018 for general safety."
    )
    result = check_response_safety(llm_text, candidates)
    assert result.is_safe is False
    assert "IS 15919:2013" in result.fabricated_standard_numbers or "IS 15919" in " ".join(result.fabricated_standard_numbers)
    assert len(result.fabricated_standard_numbers) >= 1


def test_safety_check_passes_with_no_candidates_and_no_standard_mentions():
    result = check_response_safety("Could you tell me more about the product's intended use?", [])
    assert result.is_safe is True


def test_safety_check_rejects_any_standard_mention_when_no_candidates_exist():
    result = check_response_safety("I believe IS 302-1 would apply here.", [])
    assert result.is_safe is False
    assert "IS 302-1" in result.fabricated_standard_numbers


def test_fallback_response_contains_no_fabricated_content():
    from app.product.clarification import ClarificationQuestion

    candidates = [_candidate_with_evidence_text("1 SCOPE\nsynthetic content", document_name="test_text.pdf")]
    questions = [ClarificationQuestion("product_type", "What type is it?")]

    fallback = build_fallback_response(questions, candidates)

    assert "What type is it?" in fallback
    assert "test_text.pdf" in fallback
    assert "NEEDS_CLARIFICATION".replace("_", " ").title() in fallback or "Needs Clarification" in fallback


def test_discovery_turn_substitutes_fallback_when_llm_fabricates_standard(db_session):
    """End-to-end: ChatService must never let a fabricated standard number
    reach the persisted assistant message or the API response."""
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nElectric storage water heater safety requirements.")
    llm = ScriptedFakeLLM(
        responses=[
            "product_category: water heater",
            "IS 15919:2013 - Fake Water Heater Standard definitely applies and is mandatory.",
        ]
    )
    service = ChatService(db_session, llm_provider=llm)

    response = service.send_message("electric water heater", conversation_id=None, mode="product_discovery")

    assert "IS 15919" not in response.message.content
    assert "Fake Water Heater Standard" not in response.message.content
