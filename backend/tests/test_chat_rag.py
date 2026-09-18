"""
Chat service tests — Phase 5.

Uses mocked LLM providers exclusively (never a real external API call) so
the test suite has zero dependency on network access or API keys. The mock
LLM providers here are test doubles, distinct from app.llm.mock_provider's
MockLLMProvider (though that class could also be used directly — a couple
of tests do exactly that to prove it works as documented).
"""

import uuid
from datetime import date

import pytest

from app.llm.mock_provider import MockLLMProvider
from app.llm.provider import (
    LLMMessage,
    LLMProviderError,
    LLMResponse,
    OllamaModelNotFoundError,
    OllamaNotRunningError,
)
from app.models.document_chunk import DocumentChunk
from app.models.standard import Standard
from app.models.standard_document import StandardDocument
from app.rag.retrieval import RetrievalError, RetrievalService
from app.rag.vector_store import serialize_embedding
from app.services.chat_service import ChatGenerationError, ChatNotFoundError, ChatService
from tests.test_embeddings import FakeEmbeddingProvider


class RecordingFakeLLM:
    """A test double that records what it was called with, so tests can
    assert the context/history actually reached the provider."""

    name = "fake"
    model = "fake-model"
    is_mock = True

    def __init__(self):
        self.calls = []

    def generate(self, system_prompt, conversation_history, user_message):
        self.calls.append(
            {"system_prompt": system_prompt, "conversation_history": conversation_history, "user_message": user_message}
        )
        return LLMResponse(content=f"fake answer to: {user_message}", model=self.model, provider=self.name)


class AlwaysFailingLLM:
    name = "failing"
    model = "failing-model"
    is_mock = False

    def generate(self, system_prompt, conversation_history, user_message):
        raise LLMProviderError("simulated provider failure")


class OllamaNotRunningFakeLLM:
    """Simulates an OllamaLLMProvider whose server is unreachable, without
    actually constructing one — keeps this test file free of any real HTTP
    dependency, matching how AlwaysFailingLLM simulates LLMProviderError."""

    name = "ollama"
    model = "qwen2.5:7b"
    is_mock = False

    def generate(self, system_prompt, conversation_history, user_message):
        raise OllamaNotRunningError("Could not reach Ollama at http://localhost:11434.")


class OllamaModelNotFoundFakeLLM:
    name = "ollama"
    model = "does-not-exist"
    is_mock = False

    def generate(self, system_prompt, conversation_history, user_message):
        raise OllamaModelNotFoundError("Model 'does-not-exist' was not found.")


def _make_document_with_chunk(db_session, text="1 SCOPE\nThis synthetic document defines scope.", standard_id=None):
    doc = StandardDocument(
        id=str(uuid.uuid4()),
        standard_id=standard_id,
        original_filename="synthetic_test.pdf",
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
    return doc, chunk


# --- Basic chat flow ---


def test_chat_creates_conversation_and_persists_messages(db_session):
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = RecordingFakeLLM()
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    response = service.send_message("What is the scope?", conversation_id=None)

    assert response.conversation_id
    assert response.message.role == "assistant"
    assert "fake answer to: What is the scope?" in response.message.content
    assert len(llm.calls) == 1


def test_chat_with_unknown_conversation_id_raises(db_session):
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = RecordingFakeLLM()
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    with pytest.raises(ChatNotFoundError):
        service.send_message("hello", conversation_id="does-not-exist")


def test_user_message_persisted_even_when_generation_fails(db_session):
    """If the LLM fails, the user's message must still be stored — only the
    assistant reply is withheld."""
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = AlwaysFailingLLM()
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    with pytest.raises(ChatGenerationError) as exc_info:
        service.send_message("What is the scope?", conversation_id=None)
    assert exc_info.value.code == "LLM_PROVIDER_ERROR"

    from app.models.conversation import Conversation

    conversations = db_session.query(Conversation).all()
    assert len(conversations) == 1
    assert len(conversations[0].messages) == 1  # user message only, no assistant message
    assert conversations[0].messages[0].role == "user"


# --- Retrieval integration ---


def test_chat_uses_real_retrieval_results_as_evidence(db_session):
    doc, chunk = _make_document_with_chunk(db_session)
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = RecordingFakeLLM()
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    service.send_message("This synthetic document defines scope", conversation_id=None)

    system_prompt_used = llm.calls[0]["system_prompt"]
    assert "synthetic_test.pdf" in system_prompt_used
    assert "This synthetic document defines scope" in system_prompt_used


def test_retrieval_failure_raises_retrieval_error_code(db_session):
    class FailingRetrieval:
        def retrieve(self, *args, **kwargs):
            raise RetrievalError("simulated retrieval failure")

    llm = RecordingFakeLLM()
    service = ChatService(db_session, retrieval_service=FailingRetrieval(), llm_provider=llm)

    with pytest.raises(ChatGenerationError) as exc_info:
        service.send_message("test", conversation_id=None)
    assert exc_info.value.code == "RETRIEVAL_ERROR"
    assert len(llm.calls) == 0  # LLM must never be called if retrieval failed


# --- Citations ---


def test_citations_derived_from_retrieval_not_llm(db_session):
    doc, chunk = _make_document_with_chunk(db_session)
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = RecordingFakeLLM()
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    response = service.send_message("This synthetic document defines scope", conversation_id=None)

    assert len(response.message.citations) == 1
    citation = response.message.citations[0]
    assert citation.document_id == doc.id
    assert citation.document_name == "synthetic_test.pdf"
    assert citation.page_number == 1
    assert citation.section == "1"
    assert citation.chunk_id == chunk.id


def test_no_evidence_produces_no_citations(db_session):
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = RecordingFakeLLM()
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    response = service.send_message("anything at all", conversation_id=None)

    assert response.message.citations == []
    # Grounding rule check: the context block must honestly say no evidence was found.
    assert "(none" in llm.calls[0]["system_prompt"]


# --- standard_id filtering ---


def test_standard_id_filters_retrieval_to_linked_documents(db_session):
    standard = Standard(
        id=str(uuid.uuid4()),
        code="IS 99999",
        title="Test Standard",
        category="Test",
        description="test",
        status="active",
        last_amended=date(2024, 1, 1),
        sector="Test",
        source_type="demo",
    )
    db_session.add(standard)
    db_session.commit()

    linked_doc, linked_chunk = _make_document_with_chunk(
        db_session, text="1 SCOPE\nLinked document content.", standard_id=standard.id
    )
    unlinked_doc, unlinked_chunk = _make_document_with_chunk(
        db_session, text="1 SCOPE\nUnlinked document content.", standard_id=None
    )

    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = RecordingFakeLLM()
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    response = service.send_message("scope content", conversation_id=None, standard_id=standard.id)

    cited_document_ids = {c.document_id for c in response.message.citations}
    assert cited_document_ids <= {linked_doc.id}
    assert unlinked_doc.id not in cited_document_ids


# --- LLM provider selection ---


def test_llm_not_configured_raises_correct_code(db_session):
    from app.llm.provider import get_llm_provider

    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    # No llm_provider passed to ChatService -> falls back to get_llm_provider(),
    # which raises LLMNotConfiguredError when settings.llm_provider is unset
    # (the default in this test environment — no .env file exists).
    service = ChatService(db_session, retrieval_service=retrieval)

    with pytest.raises(ChatGenerationError) as exc_info:
        service.send_message("test", conversation_id=None)
    assert exc_info.value.code == "LLM_NOT_CONFIGURED"


def test_mock_llm_provider_is_clearly_labelled():
    provider = MockLLMProvider()
    response = provider.generate(system_prompt="test", conversation_history=[], user_message="hello")
    assert provider.is_mock is True
    assert "MOCK" in response.content
    assert "DEVELOPMENT ONLY" in response.content


# --- API-level tests ---


def test_chat_endpoint_returns_503_when_llm_not_configured(client):
    response = client.post("/api/chat", json={"message": "test message"})
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "LLM_NOT_CONFIGURED"


def test_chat_endpoint_rejects_empty_message(client):
    response = client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 422


def test_chat_endpoint_rejects_oversized_message(client):
    response = client.post("/api/chat", json={"message": "x" * 5000})
    assert response.status_code == 422


def test_chat_endpoint_unknown_conversation_returns_404(client):
    response = client.post("/api/chat", json={"message": "test", "conversationId": "does-not-exist"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


# --- Phase 6: response language ---
#
# RETRIEVAL LANGUAGE != RESPONSE LANGUAGE — these tests verify that
# `language` only changes the instruction given to the LLM about output
# language, never retrieval, evidence, or citation metadata.


def test_english_chat_unaffected_when_no_language_given(db_session):
    """Existing callers that never send `language` must see identical
    behavior to Phase 5 — the default is English and it must be spelled
    out to the LLM the same way an explicit 'en' request would be."""
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = RecordingFakeLLM()
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    service.send_message("What is the scope?", conversation_id=None)

    system_prompt_used = llm.calls[0]["system_prompt"]
    assert "RESPONSE LANGUAGE: Answer in English (en)" in system_prompt_used


def test_hindi_request_reaches_llm_provider_as_language_instruction(db_session):
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = RecordingFakeLLM()
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    service.send_message("What is the scope?", conversation_id=None, language="hi")

    system_prompt_used = llm.calls[0]["system_prompt"]
    assert "RESPONSE LANGUAGE: Answer in Hindi (hi)" in system_prompt_used


def test_mock_provider_labels_hindi_response(db_session):
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=MockLLMProvider())

    response = service.send_message("What is the scope?", conversation_id=None, language="hi")

    assert "MOCK RESPONSE LANGUAGE: HINDI (hi)" in response.message.content
    assert "MOCK" in response.message.content
    assert "DEVELOPMENT ONLY" in response.message.content


def test_mock_provider_labels_english_response_by_default(db_session):
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=MockLLMProvider())

    response = service.send_message("What is the scope?", conversation_id=None)

    assert "MOCK RESPONSE LANGUAGE: ENGLISH (en)" in response.message.content


def test_retrieved_evidence_unchanged_regardless_of_response_language(db_session):
    """The evidence block itself (retrieved chunk text) must be byte-for-byte
    identical whether English or Hindi is requested — only the trailing
    language instruction differs. Guards against ever translating evidence
    before treating it as authoritative."""
    doc, chunk = _make_document_with_chunk(db_session)
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())

    llm_en = RecordingFakeLLM()
    ChatService(db_session, retrieval_service=retrieval, llm_provider=llm_en).send_message(
        "This synthetic document defines scope", conversation_id=None, language="en"
    )

    llm_hi = RecordingFakeLLM()
    ChatService(db_session, retrieval_service=retrieval, llm_provider=llm_hi).send_message(
        "This synthetic document defines scope", conversation_id=None, language="hi"
    )

    def evidence_block(system_prompt: str) -> str:
        # Strip the trailing language instruction so only the evidence
        # portion of the prompt is compared.
        return system_prompt.split("RESPONSE LANGUAGE:")[0]

    assert evidence_block(llm_en.calls[0]["system_prompt"]) == evidence_block(llm_hi.calls[0]["system_prompt"])
    assert "This synthetic document defines scope" in llm_hi.calls[0]["system_prompt"]


def test_citations_from_retrieval_unchanged_regardless_of_response_language(db_session):
    doc, chunk = _make_document_with_chunk(db_session)
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = RecordingFakeLLM()
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    response = service.send_message("This synthetic document defines scope", conversation_id=None, language="hi")

    assert len(response.message.citations) == 1
    citation = response.message.citations[0]
    assert citation.document_id == doc.id
    assert citation.document_name == "synthetic_test.pdf"
    assert citation.page_number == 1
    assert citation.section == "1"
    assert citation.chunk_id == chunk.id


def test_standard_id_filtering_still_works_with_language_selected(db_session):
    standard = Standard(
        id=str(uuid.uuid4()),
        code="IS 99998",
        title="Test Standard",
        category="Test",
        description="test",
        status="active",
        last_amended=date(2024, 1, 1),
        sector="Test",
        source_type="demo",
    )
    db_session.add(standard)
    db_session.commit()

    linked_doc, _ = _make_document_with_chunk(
        db_session, text="1 SCOPE\nLinked document content.", standard_id=standard.id
    )
    unlinked_doc, _ = _make_document_with_chunk(
        db_session, text="1 SCOPE\nUnlinked document content.", standard_id=None
    )

    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = RecordingFakeLLM()
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    response = service.send_message(
        "scope content", conversation_id=None, standard_id=standard.id, language="hi"
    )

    cited_document_ids = {c.document_id for c in response.message.citations}
    assert cited_document_ids <= {linked_doc.id}
    assert unlinked_doc.id not in cited_document_ids


def test_no_evidence_still_returns_no_citations_with_language_selected(db_session):
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = RecordingFakeLLM()
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    response = service.send_message("anything at all", conversation_id=None, language="hi")

    assert response.message.citations == []


def test_llm_not_configured_error_unaffected_by_language(db_session):
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    service = ChatService(db_session, retrieval_service=retrieval)

    with pytest.raises(ChatGenerationError) as exc_info:
        service.send_message("test", conversation_id=None, language="hi")
    assert exc_info.value.code == "LLM_NOT_CONFIGURED"


def test_chat_endpoint_accepts_hindi_language(client):
    response = client.post("/api/chat", json={"message": "test message", "language": "hi"})
    # No LLM configured in the test environment -> 503, but the request
    # itself must pass validation (language is a supported code).
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"


def test_chat_endpoint_rejects_unsupported_language(client):
    response = client.post("/api/chat", json={"message": "test message", "language": "fr"})
    assert response.status_code == 422


def test_chat_endpoint_omitted_language_still_works(client):
    response = client.post("/api/chat", json={"message": "test message"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"


# --- Phase 7: local Ollama provider error handling ---
#
# These use test doubles that raise the same exception types
# OllamaLLMProvider raises — real HTTP mocking of OllamaLLMProvider itself
# lives in test_ollama_provider.py. Here we only verify ChatService maps
# those exceptions to the correct structured error code, the same way it
# already does for LLMProviderError/RetrievalError/LLMNotConfiguredError.


def test_ollama_not_running_raises_correct_code(db_session):
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=OllamaNotRunningFakeLLM())

    with pytest.raises(ChatGenerationError) as exc_info:
        service.send_message("What is the scope?", conversation_id=None)
    assert exc_info.value.code == "OLLAMA_NOT_RUNNING"


def test_ollama_model_not_found_raises_correct_code(db_session):
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=OllamaModelNotFoundFakeLLM())

    with pytest.raises(ChatGenerationError) as exc_info:
        service.send_message("What is the scope?", conversation_id=None)
    assert exc_info.value.code == "OLLAMA_MODEL_NOT_FOUND"


def test_ollama_errors_leave_only_user_message_persisted(db_session):
    """Same persistence contract as any other generation failure — the
    user's message is kept, no assistant message/citations are created."""
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=OllamaNotRunningFakeLLM())

    with pytest.raises(ChatGenerationError):
        service.send_message("What is the scope?", conversation_id=None)

    from app.models.conversation import Conversation

    conversations = db_session.query(Conversation).all()
    assert len(conversations) == 1
    assert len(conversations[0].messages) == 1
    assert conversations[0].messages[0].role == "user"


def test_chat_endpoint_returns_503_when_ollama_not_running(client, monkeypatch):
    import app.api.routes.chat as chat_route

    original_service_cls = chat_route.ChatService

    class PatchedChatService(original_service_cls):
        def __init__(self, db):
            super().__init__(db, llm_provider=OllamaNotRunningFakeLLM())

    monkeypatch.setattr(chat_route, "ChatService", PatchedChatService)

    response = client.post("/api/chat", json={"message": "test message"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "OLLAMA_NOT_RUNNING"


# --- Phase 7: citations/standard_id/history unaffected by provider choice ---
#
# These mirror the equivalent Phase 5/6 tests exactly, but with an
# Ollama-shaped provider double, to confirm citation generation and
# standard_id filtering are provider-agnostic — they depend only on
# RetrievedChunk, never on which LLMProvider produced the answer.


def test_citations_unchanged_with_ollama_shaped_provider(db_session):
    doc, chunk = _make_document_with_chunk(db_session)
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = RecordingFakeLLM()
    llm.name, llm.model, llm.is_mock = "ollama", "qwen2.5:7b", False
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    response = service.send_message("This synthetic document defines scope", conversation_id=None)

    assert len(response.message.citations) == 1
    citation = response.message.citations[0]
    assert citation.document_id == doc.id
    assert citation.document_name == "synthetic_test.pdf"
    assert citation.chunk_id == chunk.id


def test_standard_id_filtering_unchanged_with_ollama_shaped_provider(db_session):
    standard = Standard(
        id=str(uuid.uuid4()),
        code="IS 99997",
        title="Test Standard",
        category="Test",
        description="test",
        status="active",
        last_amended=date(2024, 1, 1),
        sector="Test",
        source_type="demo",
    )
    db_session.add(standard)
    db_session.commit()

    linked_doc, _ = _make_document_with_chunk(
        db_session, text="1 SCOPE\nLinked document content.", standard_id=standard.id
    )
    unlinked_doc, _ = _make_document_with_chunk(
        db_session, text="1 SCOPE\nUnlinked document content.", standard_id=None
    )

    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())
    llm = RecordingFakeLLM()
    llm.name, llm.model, llm.is_mock = "ollama", "qwen2.5:7b", False
    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=llm)

    response = service.send_message("scope content", conversation_id=None, standard_id=standard.id)

    cited_document_ids = {c.document_id for c in response.message.citations}
    assert cited_document_ids <= {linked_doc.id}
    assert unlinked_doc.id not in cited_document_ids


def test_plain_chat_flags_fabricated_standard_without_discarding_answer(db_session):
    """The plain (non-product-discovery) chat path had no fabrication
    check at all until this test was added — confirmed via live testing
    against a real local model, which invented a standard number
    ("IS 14587:1998") not present in the retrieved evidence for a real
    question. This reproduces that exact failure mode with a scripted
    fake LLM so it cannot regress silently.

    The response is kept and marked rather than replaced: discarding it
    wholesale also discarded correctly cited content, and the bare document
    list that took its place answered nothing."""
    _make_document_with_chunk(db_session, text="1 SCOPE\nPackaged drinking water quality requirements.")
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())

    class FabricatingFakeLLM:
        name = "fake"
        model = "fake-model"
        is_mock = True

        def generate(self, system_prompt, conversation_history, user_message):
            return LLMResponse(
                content="You should refer to IS 14587:1998 for packaged drinking water bottles.",
                model=self.model,
                provider=self.name,
            )

    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=FabricatingFakeLLM())

    response = service.send_message("Which standard applies to packaged drinking water bottles?", conversation_id=None)

    assert "Unverified" in response.message.content
    assert "IS 14587:1998" in response.message.content


def test_plain_chat_allows_response_naming_a_standard_actually_in_evidence(db_session):
    """The safety check must not reject an honest response just because it
    mentions a standard number — only a number absent from the retrieved
    evidence is fabricated. The chunk text itself contains "IS 14625"
    (a real number in this turn's evidence), so a response naming that
    same number must pass through unmodified."""
    _make_document_with_chunk(
        db_session, text="1 SCOPE\nThis standard IS 14625 covers packaged drinking water quality requirements."
    )
    retrieval = RetrievalService(db_session, embedding_provider=FakeEmbeddingProvider())

    class HonestFakeLLM:
        name = "fake"
        model = "fake-model"
        is_mock = True

        def generate(self, system_prompt, conversation_history, user_message):
            return LLMResponse(
                content="IS 14625 covers packaged drinking water quality requirements.",
                model=self.model,
                provider=self.name,
            )

    service = ChatService(db_session, retrieval_service=retrieval, llm_provider=HonestFakeLLM())

    response = service.send_message("Which standard covers packaged drinking water?", conversation_id=None)

    assert "IS 14625" in response.message.content


def test_history_persistence_unchanged_with_ollama_shaped_provider(client, db_session, monkeypatch):
    import app.api.routes.chat as chat_route

    llm = RecordingFakeLLM()
    llm.name, llm.model, llm.is_mock = "ollama", "qwen2.5:7b", False
    original_service_cls = chat_route.ChatService

    class PatchedChatService(original_service_cls):
        def __init__(self, db):
            super().__init__(db, llm_provider=llm)

    monkeypatch.setattr(chat_route, "ChatService", PatchedChatService)

    chat_response = client.post("/api/chat", json={"message": "hello there"})
    assert chat_response.status_code == 200
    conversation_id = chat_response.json()["conversationId"]

    history_response = client.get(f"/api/history/{conversation_id}")
    assert history_response.status_code == 200
    body = history_response.json()
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][1]["role"] == "assistant"
