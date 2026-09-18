"""
Phase 12 tests — BIS knowledge base & regulatory evidence layer.

Uses hand-written LLM test doubles exclusively (matching earlier phases'
conventions), never a real external API call. Reuses ScriptedFakeLLM and
_make_document_with_chunk from tests/test_product_discovery.py and
_candidate from tests/test_compliance_requirements.py rather than
duplicating them.

All evidence used here is SYNTHETIC TEST DATA — never a real BIS document.
This suite proves the knowledge-taxonomy/provenance/normalization/
retrieval-prioritization PIPELINE works; it makes no claim about real BIS
compliance coverage, regulatory status, or standard applicability.
"""

import uuid
from datetime import datetime, timezone

from app.models.product_profile import ProductProfile
from app.models.regulatory_evidence import DEFAULT_MANDATORY_STATUS, RegulatoryEvidence
from app.models.standard_document import StandardDocument
from app.product.document_type import DocumentType
from app.product.hybrid_retrieval import find_candidates
from app.product.product_taxonomy import normalize_category, normalize_intended_use, normalize_water_heater_type
from app.product.profile_extraction import apply_updates
from app.product.query_classification import prioritized_document_types
from app.rag.retrieval import RetrievalService
from app.repositories.document_repository import DocumentRepository
from app.repositories.regulatory_evidence_repository import RegulatoryEvidenceRepository
from app.services.document_service import DocumentService, InvalidDocumentTypeError
from tests.test_compliance_requirements import _candidate
from tests.test_embeddings import FakeEmbeddingProvider
from tests.test_product_discovery import ScriptedFakeLLM, _make_document_with_chunk


def _read_fixture(name: str) -> bytes:
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / name).read_bytes()


# --- 1. Document type classification ---


def test_upload_with_explicit_document_type(db_session, isolated_storage):
    service = DocumentService(db_session)
    content = _read_fixture("test_text.pdf")

    document = service.register_upload(
        content, "test_text.pdf", "application/pdf", document_type=DocumentType.INDIAN_STANDARD.value
    )

    assert document.document_type == "INDIAN_STANDARD"


def test_upload_without_document_type_defaults_to_other(db_session, isolated_storage):
    service = DocumentService(db_session)
    content = _read_fixture("test_text.pdf")

    document = service.register_upload(content, "test_text.pdf", "application/pdf")

    assert document.document_type == "OTHER"


def test_upload_rejects_unsupported_document_type(db_session, isolated_storage):
    service = DocumentService(db_session)
    content = _read_fixture("test_text.pdf")

    try:
        service.register_upload(content, "test_text.pdf", "application/pdf", document_type="NOT_A_REAL_TYPE")
        assert False, "expected InvalidDocumentTypeError"
    except InvalidDocumentTypeError:
        pass


def test_upload_endpoint_accepts_document_type_form_field(client, isolated_storage):
    content = _read_fixture("test_text.pdf")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test_text.pdf", content, "application/pdf")},
        data={"document_type": "QCO"},
    )
    assert response.status_code == 201
    assert response.json()["document_type"] == "QCO"


def test_upload_endpoint_rejects_invalid_document_type(client, isolated_storage):
    content = _read_fixture("test_text.pdf")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test_text.pdf", content, "application/pdf")},
        data={"document_type": "NOT_REAL"},
    )
    assert response.status_code == 422


# --- 2. Provenance persistence ---


def test_provenance_fields_persisted(db_session, isolated_storage):
    service = DocumentService(db_session)
    content = _read_fixture("test_text.pdf")

    document = service.register_upload(
        content, "test_text.pdf", "application/pdf", document_type=DocumentType.INDIAN_STANDARD.value, source="manual upload by admin"
    )

    assert document.source == "manual upload by admin"
    assert document.acquisition_date is not None
    # No source_url was provided at upload time -> stays null, never fabricated.
    assert document.source_url is None


def test_provenance_not_exposed_via_filesystem_path(db_session, isolated_storage):
    service = DocumentService(db_session)
    content = _read_fixture("test_text.pdf")
    document = service.register_upload(content, "test_text.pdf", "application/pdf")
    assert not hasattr(document, "storage_path")


# --- 3. Standard metadata (existing Phase 8 fields unaffected) ---


def test_standard_metadata_fields_still_present_alongside_document_type(db_session, isolated_storage):
    service = DocumentService(db_session)
    content = _read_fixture("test_text.pdf")
    document = service.register_upload(
        content, "test_text.pdf", "application/pdf", document_type=DocumentType.INDIAN_STANDARD.value
    )
    result = service.process_document(document.id, content)

    assert result.extracted_standard_number == "IS 99999"
    assert result.document_type == "INDIAN_STANDARD"


# --- 4. Regulatory metadata ---


def test_regulatory_evidence_can_be_created_and_linked(db_session, isolated_storage):
    service = DocumentService(db_session)
    content = _read_fixture("test_text.pdf")
    document_response = service.register_upload(
        content, "test_text.pdf", "application/pdf", document_type=DocumentType.QCO.value
    )

    repo = RegulatoryEvidenceRepository(db_session)
    evidence = RegulatoryEvidence(
        id=str(uuid.uuid4()),
        document_id=document_response.id,
        regulatory_reference="Synthetic QCO Reference (test only)",
        product_scope="Synthetic test product scope",
        effective_date=datetime.now(timezone.utc),
        scheme="Synthetic Scheme",
        notes="SYNTHETIC TEST DATA — NOT AN OFFICIAL BIS REGULATORY RECORD",
    )
    repo.create(evidence)

    fetched = repo.get_by_document_id(document_response.id)
    assert fetched is not None
    assert fetched.regulatory_reference == "Synthetic QCO Reference (test only)"


# --- 5. Mandatory status defaulting to NOT_DETERMINED ---


def test_regulatory_evidence_defaults_to_not_determined(db_session, isolated_storage):
    service = DocumentService(db_session)
    content = _read_fixture("test_text.pdf")
    document_response = service.register_upload(content, "test_text.pdf", "application/pdf")

    evidence = RegulatoryEvidence(id=str(uuid.uuid4()), document_id=document_response.id)
    RegulatoryEvidenceRepository(db_session).create(evidence)

    assert evidence.mandatory_status == DEFAULT_MANDATORY_STATUS
    assert evidence.mandatory_status == "NOT_DETERMINED"


def test_no_code_path_ever_sets_mandatory_confirmed_automatically(db_session, isolated_storage):
    """Confirms no ingestion/pipeline code creates a RegulatoryEvidence row
    at all — it must only ever come from an explicit administrative
    action, per this module's governance."""
    service = DocumentService(db_session)
    content = _read_fixture("test_text.pdf")
    document_response = service.register_upload(content, "test_text.pdf", "application/pdf")
    service.process_document(document_response.id, content)

    repo = RegulatoryEvidenceRepository(db_session)
    assert repo.get_by_document_id(document_response.id) is None


# --- 6. No automatic verified_bis assignment ---


def test_document_type_assignment_never_changes_source_type(db_session, isolated_storage):
    service = DocumentService(db_session)
    content = _read_fixture("test_text.pdf")

    document = service.register_upload(
        content, "test_text.pdf", "application/pdf", document_type=DocumentType.INDIAN_STANDARD.value
    )

    assert document.source_type == "unverified"
    assert document.source_type != "verified_bis"


def test_upload_endpoint_never_returns_verified_bis(client, isolated_storage):
    content = _read_fixture("test_text.pdf")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test_text.pdf", content, "application/pdf")},
        data={"document_type": "INDIAN_STANDARD"},
    )
    assert response.json()["source_type"] != "verified_bis"


# --- 7. Product category normalization ---


def test_normalize_category_maps_synonym_to_controlled_value():
    assert normalize_category("electric water heater") == "water_heater"
    assert normalize_category("storage water heater") == "water_heater"
    assert normalize_category("domestic water heating appliance") == "water_heater"


def test_normalize_category_maps_water_purifier_synonyms():
    assert normalize_category("RO water purifier") == "water_purifier"
    assert normalize_category("water filter") == "water_purifier"


# --- 8. Synonym normalization applied during profile extraction ---


def test_profile_extraction_normalizes_category_before_storage():
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()))
    apply_updates(profile, {"product_category": "domestic water heating appliance"})
    assert profile.product_category == "water_heater"


def test_profile_extraction_normalizes_type_and_use_for_known_category():
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()))
    apply_updates(profile, {"product_category": "electric water heater"})
    apply_updates(profile, {"product_type": "storage-type", "intended_use": "household use"})
    assert profile.product_type == "storage"
    assert profile.intended_use == "domestic"


# --- 9. Unknown category behavior ---


def test_unrecognized_category_stored_as_is_and_falls_back_to_generic_questions():
    from app.product.clarification import missing_field_questions

    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()))
    apply_updates(profile, {"product_category": "some unrelated gadget"})

    assert profile.product_category == "some unrelated gadget"  # never discarded, never guessed
    questions = missing_field_questions(profile)
    assert len(questions) > 0  # falls back to FALLBACK_QUESTIONS, not silently empty


def test_normalize_category_returns_none_for_unrecognized_text():
    assert normalize_category("some unrelated gadget") is None
    assert normalize_category(None) is None
    assert normalize_category("") is None


# --- 10. Product attribute normalization ---


def test_normalize_intended_use_domestic_and_commercial():
    assert normalize_intended_use("for home use") == "domestic"
    assert normalize_intended_use("for commercial use") == "commercial"
    assert normalize_intended_use("something else entirely") is None


def test_normalize_water_heater_type_storage_and_instant():
    assert normalize_water_heater_type("storage tank type") == "storage"
    assert normalize_water_heater_type("instant/tankless") == "instant"
    assert normalize_water_heater_type("unclear description") is None


# --- 11. Retrieval using document type ---


def test_retrieval_filters_by_document_types(db_session):
    doc_a, chunk_a = _make_document_with_chunk(db_session, text="1 SCOPE\nStandard content A.", filename="a.pdf")
    doc_b, chunk_b = _make_document_with_chunk(db_session, text="1 SCOPE\nStandard content A.", filename="b.pdf")
    doc_a.document_type = DocumentType.INDIAN_STANDARD.value
    doc_b.document_type = DocumentType.QCO.value
    db_session.commit()

    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    results = retrieval.retrieve(query="Standard content A", top_k=10, document_types=[DocumentType.QCO.value])

    result_doc_ids = {r.document_id for r in results}
    assert doc_b.id in result_doc_ids
    assert doc_a.id not in result_doc_ids


def test_retrieval_document_types_empty_list_returns_no_results(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nSome content.")
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    results = retrieval.retrieve(query="Some content", top_k=10, document_types=[])
    assert results == []


def test_retrieval_without_document_types_unaffected(db_session):
    """Existing callers that never pass document_types must see identical
    behavior — the exact Phase 4/5 retrieval contract."""
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nThis synthetic document defines scope.")
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    results = retrieval.retrieve(query="This synthetic document defines scope", top_k=4)
    assert len(results) == 1
    assert results[0].document_id == doc.id


# --- 12. Retrieval using metadata (document_type carried on RetrievedChunk) ---


def test_retrieved_chunk_carries_document_type(db_session):
    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nContent about testing.")
    doc.document_type = DocumentType.TESTING_GUIDANCE.value
    db_session.commit()

    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    results = retrieval.retrieve(query="Content about testing", top_k=4)

    assert len(results) == 1
    assert results[0].document_type == "TESTING_GUIDANCE"


# --- 13. Regulatory query prioritization ---


def test_query_classification_prioritizes_regulatory_types_for_mandatory_question():
    prioritized = prioritized_document_types("Is BIS certification mandatory for this product?")
    assert "QCO" in prioritized
    assert "REGULATORY_ORDER" in prioritized


def test_query_classification_prioritizes_procedural_types_for_application_question():
    prioritized = prioritized_document_types("How do I apply for certification?")
    assert "BIS_SCHEME" in prioritized


# --- 14. Standard/technical query prioritization ---


def test_query_classification_prioritizes_technical_types_for_requirement_question():
    prioritized = prioritized_document_types("What technical requirement applies to this test method?")
    assert "INDIAN_STANDARD" in prioritized
    assert "TESTING_GUIDANCE" in prioritized


def test_query_classification_returns_empty_for_unrelated_query():
    assert prioritized_document_types("Hello, how are you?") == set()


def test_hybrid_retrieval_boosts_prioritized_document_type(db_session):
    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water_heater")
    db_session.add(profile)
    db_session.commit()

    doc_a, _ = _make_document_with_chunk(db_session, text="1 SCOPE\nwater heater general info.", filename="standard.pdf")
    doc_b, _ = _make_document_with_chunk(db_session, text="1 SCOPE\nwater heater general info.", filename="qco.pdf")
    doc_a.document_type = DocumentType.INDIAN_STANDARD.value
    doc_b.document_type = DocumentType.QCO.value
    db_session.commit()

    candidates = find_candidates(db_session, profile, top_k=10, user_query="Is certification mandatory?")

    # The QCO-typed document should be boosted ahead of the plain standard
    # for a mandatory-status question, even with identical evidence text.
    qco_index = next(i for i, c in enumerate(candidates) if c.document_id == doc_b.id)
    standard_index = next(i for i, c in enumerate(candidates) if c.document_id == doc_a.id)
    assert qco_index < standard_index


# --- 15. Citation preservation ---


def test_citations_unaffected_by_document_type_field(db_session):
    from app.llm.provider import LLMResponse
    from app.services.chat_service import ChatService

    doc, chunk = _make_document_with_chunk(db_session, text="1 SCOPE\nThis synthetic document defines scope.")
    doc.document_type = DocumentType.INDIAN_STANDARD.value
    db_session.commit()

    class EchoLLM:
        name, model, is_mock = "fake", "fake", True

        def generate(self, system_prompt, conversation_history, user_message):
            return LLMResponse(content="answer", model=self.model, provider=self.name)

    service = ChatService(
        db_session, retrieval_service=RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider()), llm_provider=EchoLLM()
    )
    response = service.send_message("This synthetic document defines scope", conversation_id=None)

    assert len(response.message.citations) == 1
    assert response.message.citations[0].document_id == doc.id
    assert response.message.citations[0].chunk_id == chunk.id


# --- 16. Existing requirement extraction unaffected ---


def test_requirement_extraction_unaffected_by_document_type(db_session):
    from app.product.applicability import ApplicabilityStatus
    from app.product.requirement_extraction import extract_requirements

    candidate = _candidate(
        "4.2 Testing\nThe sample shall be tested for electrical safety.", ApplicabilityStatus.POTENTIALLY_APPLICABLE
    )
    requirements = extract_requirements([candidate])
    assert len(requirements) >= 1


# --- 17. Existing checklist behavior unaffected ---


def test_checklist_still_builds_with_document_type_present(db_session):
    from app.product.applicability import ApplicabilityStatus
    from app.product.checklist import build_checklist

    profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), product_category="water_heater")
    candidate = _candidate(
        "4.2 Testing\nThe sample shall be tested.", ApplicabilityStatus.POTENTIALLY_APPLICABLE
    )
    checklist = build_checklist(profile, [candidate], open_questions=[])
    assert len(checklist.items) >= 1


# --- 18. Existing safety filters unaffected ---


def test_safety_filter_still_works_after_knowledge_base_changes():
    from app.product.response_safety import check_response_safety

    result = check_response_safety("IS 55555 definitely applies.", [])
    assert result.is_safe is False


# --- 19. Existing document management unaffected ---


def test_document_list_and_delete_unaffected_by_document_type(client, isolated_storage):
    content = _read_fixture("test_text.pdf")
    upload_response = client.post(
        "/api/documents/upload",
        files={"file": ("test_text.pdf", content, "application/pdf")},
        data={"document_type": "PRODUCT_MANUAL"},
    )
    document_id = upload_response.json()["id"]

    list_response = client.get("/api/documents")
    assert list_response.status_code == 200
    assert list_response.json()[0]["document_type"] == "PRODUCT_MANUAL"

    delete_response = client.delete(f"/api/documents/{document_id}")
    assert delete_response.status_code == 204


# --- 20. Existing Ollama provider unaffected ---


def test_ollama_provider_still_importable():
    from app.llm.ollama_provider import OllamaLLMProvider

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    assert provider.name == "ollama"
