"""
Chat service — Phase 5: real retrieval + real LLM generation (when
configured), replacing Phase 2's keyword-matched demo responder.

Workflow (per docs/CHAT_RAG.md):
  1. create or load conversation
  2. store user message
  3. run retrieval (RetrievalService) for BIS-specific evidence
  4. build grounded context (app/llm/grounding.py, app/llm/context_builder.py)
  5. call the configured LLMProvider
  6. store assistant message + citations (from retrieval results, never
     invented by the LLM)
  7. return response

If the LLM is not configured, or the provider call fails, no assistant
message is stored — the user's message is still persisted (so the
conversation state stays consistent), but the caller receives a
structured error, never a fabricated assistant reply.

ChatService intentionally contains no raw database queries, no
provider-specific LLM code, and no embedding implementation — those stay
behind RetrievalService, LLMProvider, and the repository layer,
respectively.

Phase 10 adds product-discovery mode as an extension of the SAME
send_message() workflow above, not a parallel implementation: a
conversation enters discovery mode when the request explicitly sets
mode="product_discovery" (see app/schemas/chat.py), or — on any later turn
— when that conversation already has a ProductProfile row from an earlier
discovery-mode message. In discovery mode, step 3 becomes hybrid retrieval
(app/product/hybrid_retrieval.py) driven by the ProductProfile's derived
search terms instead of the raw user message, and step 4's system prompt
is built by app/product/discovery_response.py instead of the plain BIS
grounding prompt. Steps 1, 2, 5, 6, 7 — conversation/message persistence,
LLM provider selection, and citation-from-RetrievedChunk construction —
are completely unchanged and shared by both modes. Ordinary BIS Q&A chat
(no mode field, no existing ProductProfile) is byte-for-byte the same
Phase 5/6/7 code path it always was.
"""

import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.context_builder import chunks_to_context_dicts, truncate_history
from app.llm.grounding import SYSTEM_PROMPT, build_context_block, build_language_instruction
from app.llm.provider import (
    LLMMessage,
    LLMNotConfiguredError,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    OllamaModelNotFoundError,
    OllamaNotRunningError,
    get_llm_provider,
)
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.models.message_citation import MessageCitation
from app.models.product_profile import ProductProfile
from app.product.applicability import evaluate_candidates
from app.product.checklist import build_checklist
from app.product.clarification import ClarificationQuestion, has_sufficient_information, missing_field_questions
from app.product.discovery_response import DISCOVERY_SYSTEM_PROMPT, build_discovery_context_block
from app.product.external_standard_fallback import should_attempt_fallback, try_ingest_external_match
from app.product.hybrid_retrieval import find_candidates
from app.product.profile_extraction import apply_updates, extract_profile_updates
from app.product.response_safety import (
    append_unverified_standards_warning,
    build_fallback_response,
    check_plain_chat_response_safety,
    check_response_safety,
    trim_off_corpus_speculation,
)
from app.rag.retrieval import RetrievalError, RetrievalService, looks_off_corpus
from app.repositories.citation_repository import CitationRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.product_profile_repository import ProductProfileRepository
from app.schemas.candidate_standard import CandidateStandard
from app.schemas.chat import (
    CHAT_MODE_PRODUCT_DISCOVERY,
    DEFAULT_LANGUAGE,
    ChatResponse,
    CitationResponse,
    MessageResponse,
)
from app.schemas.compliance import ComplianceChecklist
from app.schemas.product_profile import ProductProfileResponse
from app.schemas.retrieval import RetrievedChunk

logger = logging.getLogger("bis_sahayak")

MAX_TITLE_LENGTH = 60
RETRIEVAL_TOP_K = 4
DISCOVERY_TOP_K = 6


def _derive_title(first_message: str) -> str:
    trimmed = first_message.strip()
    if len(trimmed) <= MAX_TITLE_LENGTH:
        return trimmed
    return trimmed[:MAX_TITLE_LENGTH].rstrip() + "…"


class ChatNotFoundError(Exception):
    pass


class ChatGenerationError(Exception):
    """Raised when the assistant could not produce a response — LLM not
    configured, provider failure, or retrieval failure. Carries a `code`
    matching the API error contract (LLM_NOT_CONFIGURED, LLM_PROVIDER_ERROR,
    RETRIEVAL_ERROR, OLLAMA_NOT_RUNNING, OLLAMA_MODEL_NOT_FOUND) so the
    route can map it to the right structured error."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class ChatService:
    def __init__(
        self,
        db: Session,
        retrieval_service: RetrievalService | None = None,
        llm_provider: LLMProvider | None = None,
    ):
        self.db = db
        self.conversations = ConversationRepository(db)
        self.messages = MessageRepository(db)
        self.citations = CitationRepository(db)
        self.product_profiles = ProductProfileRepository(db)
        self._retrieval_service = retrieval_service
        self._llm_provider = llm_provider

    def send_message(
        self,
        user_text: str,
        conversation_id: str | None,
        standard_id: str | None = None,
        language: str | None = None,
        mode: str | None = None,
        user_id: str | None = None,
    ) -> ChatResponse:
        conversation = self._get_or_create_conversation(user_text, conversation_id, user_id)

        user_message = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            role=MessageRole.user.value,
            content=user_text,
        )
        self.messages.create(user_message)

        # --- Phase 10: product-discovery mode detection ---
        # A conversation enters discovery mode either by explicit request
        # (mode="product_discovery") or because an earlier turn in this
        # same conversation already created a ProductProfile — so the
        # client never has to resend the mode flag on every message for it
        # to keep evolving. Neither condition can ever trigger for a
        # conversation that never opted in, so ordinary BIS chat is
        # unaffected.
        profile = self.product_profiles.get_by_conversation_id(conversation.id)
        if profile is None and mode == CHAT_MODE_PRODUCT_DISCOVERY:
            profile = ProductProfile(id=str(uuid.uuid4()), conversation_id=conversation.id)
            profile = self.product_profiles.create(profile)

        if profile is not None:
            return self._send_discovery_message(conversation, user_message, user_text, profile, standard_id, language)

        # --- Retrieval ---
        retrieval_service = self._retrieval_service or RetrievalService(self.db)
        retrieval_start = time.monotonic()
        try:
            retrieved_chunks = retrieval_service.retrieve(
                query=user_text, top_k=RETRIEVAL_TOP_K, standard_id=standard_id
            )
        except RetrievalError as exc:
            logger.warning("Retrieval failed for conversation %s: %s", conversation.id, exc)
            raise ChatGenerationError("RETRIEVAL_ERROR", f"Retrieval failed: {exc}") from exc
        retrieval_duration_ms = (time.monotonic() - retrieval_start) * 1000
        logger.info(
            "conversation=%s retrieved=%d chunks in %.1fms",
            conversation.id,
            len(retrieved_chunks),
            retrieval_duration_ms,
        )

        # --- LLM provider ---
        try:
            llm_provider = self._llm_provider or get_llm_provider()
        except LLMNotConfiguredError as exc:
            raise ChatGenerationError("LLM_NOT_CONFIGURED", str(exc)) from exc

        # --- Context construction ---
        # Retrieval always runs against original document text above —
        # RETRIEVAL LANGUAGE != RESPONSE LANGUAGE. The language instruction
        # is appended after the untrusted evidence block, built
        # independently of it, so it cannot be confused with retrieved
        # document content.
        off_corpus = looks_off_corpus(user_text, retrieved_chunks)
        if off_corpus:
            logger.info(
                "conversation=%s retrieved evidence is not about the question (top score %.4f, "
                "%s) — answering in not-covered mode",
                conversation.id,
                retrieved_chunks[0].similarity_score,
                ", ".join(sorted({c.document_name for c in retrieved_chunks})),
            )

        context_dicts = chunks_to_context_dicts(retrieved_chunks)
        context_block = build_context_block(context_dicts, off_corpus=off_corpus)
        language_instruction = build_language_instruction(language or DEFAULT_LANGUAGE)
        system_prompt = f"{SYSTEM_PROMPT}\n\n{context_block}\n\n{language_instruction}"

        history_pairs = [(m.role, m.content) for m in conversation.messages if m.id != user_message.id]
        history_pairs = truncate_history(history_pairs)
        conversation_history = [LLMMessage(role=role, content=content) for role, content in history_pairs]

        llm_response = self._generate(llm_provider, system_prompt, conversation_history, user_text, conversation.id)

        # When the evidence is not about the question, the only defensible
        # answer is that the corpus does not cover it. The prompt asks for
        # exactly that and the model still appends remembered BIS marks,
        # laboratory names and certification steps, so the continuation is
        # cut here instead of trusted away.
        if off_corpus:
            trimmed = trim_off_corpus_speculation(llm_response.content)
            if trimmed != llm_response.content:
                logger.info("conversation=%s trimmed speculative continuation from off-corpus answer", conversation.id)
                llm_response = LLMResponse(
                    content=trimmed, model=llm_response.model, provider=llm_response.provider
                )

        # --- Safety filter ---
        # Confirmed via live testing (the same class of issue product-
        # discovery mode was already guarded against) that this plain
        # chat path had no fabrication check at all: a real question
        # produced a response inventing a standard number ("IS
        # 14587:1998") that was never in the retrieved evidence. Only the
        # fabricated-standard-number check applies here — see
        # check_plain_chat_response_safety's docstring for why the other
        # discovery-mode-specific checks don't have an equivalent in
        # plain chat.
        fabricated_numbers = check_plain_chat_response_safety(llm_response.content, retrieved_chunks)
        if fabricated_numbers:
            logger.warning(
                "conversation=%s plain chat response mentions standards absent from evidence: %s",
                conversation.id,
                fabricated_numbers,
            )
            # Warn rather than discard. Replacing the whole answer threw away
            # correct, well-cited content because of one bad number, and the
            # bare document list that replaced it answered nothing. The
            # unverifiable numbers are named explicitly so the reader knows
            # which parts not to trust.
            llm_response = LLMResponse(
                content=append_unverified_standards_warning(llm_response.content, fabricated_numbers),
                model=llm_response.model,
                provider=llm_response.provider,
            )

        assistant_message, citation_responses = self._persist_assistant_response(conversation, llm_response, retrieved_chunks)

        return ChatResponse(
            conversation_id=conversation.id,
            message=MessageResponse(
                id=assistant_message.id,
                role=assistant_message.role,
                content=assistant_message.content,
                timestamp=assistant_message.created_at,
                citations=citation_responses,
            ),
        )

    def _find_candidates_with_external_fallback(
        self, profile: ProductProfile, standard_id: str | None, user_text: str
    ) -> list[CandidateStandard]:
        """Runs the normal local hybrid-retrieval + applicability step,
        then — only if nothing locally ingested turned out relevant (see
        app.product.external_standard_fallback.should_attempt_fallback) —
        tries to ingest a real matching standard from Internet Archive and
        re-runs local retrieval once so the new document is found the
        ordinary way. A fallback that finds or ingests nothing silently
        falls through to returning the original (empty/low-relevance)
        candidates — this is a best-effort enhancement, never required."""
        candidates = find_candidates(self.db, profile, top_k=DISCOVERY_TOP_K, standard_id=standard_id, user_query=user_text)
        candidates = evaluate_candidates(candidates, profile)

        if get_settings().external_standard_fallback_enabled and should_attempt_fallback(candidates, profile):
            new_document_id = try_ingest_external_match(self.db, profile)
            if new_document_id is not None:
                candidates = find_candidates(
                    self.db, profile, top_k=DISCOVERY_TOP_K, standard_id=standard_id, user_query=user_text
                )
                candidates = evaluate_candidates(candidates, profile)

        return candidates

    def _send_discovery_message(
        self,
        conversation: Conversation,
        user_message: Message,
        user_text: str,
        profile: ProductProfile,
        standard_id: str | None,
        language: str | None,
    ) -> ChatResponse:
        """Phase 10 product-discovery turn. Shares LLM-provider selection
        and the final generate+persist+cite steps with the plain BIS chat
        path (see _generate/_persist_assistant_response) — only retrieval
        and system-prompt construction differ."""
        # --- Profile extraction (schema-validated, never arbitrary fields — see profile_extraction.py) ---
        try:
            llm_provider = self._llm_provider or get_llm_provider()
        except LLMNotConfiguredError as exc:
            raise ChatGenerationError("LLM_NOT_CONFIGURED", str(exc)) from exc

        updates = extract_profile_updates(llm_provider, user_text)
        _changed_fields, conflict_questions = apply_updates(profile, updates)
        self.product_profiles.save(profile)

        # --- Clarification check ---
        # Phase 13: a genuine attribute conflict (e.g. "domestic" ->
        # "commercial", or a category conflict neither taxonomy value can
        # resolve — see app/product/specificity.py) is asked about first,
        # before any regular missing-field question, since resolving a
        # conflict is more urgent than gathering a still-unknown attribute.
        # conflict_questions are plain strings (not tied to one specific
        # missing field) — wrapped as ClarificationQuestion(field="") so
        # they flow through the exact same downstream code
        # (build_discovery_context_block, build_fallback_response,
        # clarification_questions response field) as ordinary questions.
        questions = [ClarificationQuestion(field="", question=q) for q in conflict_questions] + missing_field_questions(
            profile
        )

        # --- Hybrid retrieval + applicability (rule-based, never from the LLM) ---
        candidates = self._find_candidates_with_external_fallback(profile, standard_id, user_text)

        # --- Phase 11: compliance checklist ---
        # Only assembled once has_sufficient_information() is true — the
        # same gate Phase 10 already uses to stop asking clarification
        # questions. Requirement extraction is pure keyword/pattern
        # matching (see app/product/requirement_extraction.py) — it cannot
        # fabricate a category or requirement that isn't literally
        # suggested by the evidence text.
        checklist: ComplianceChecklist | None = None
        # A pending conflict question (Phase 13) means the profile is in a
        # genuinely unresolved state — assembling a checklist before the
        # user resolves it would build on a value that might be about to
        # change.
        if not conflict_questions and has_sufficient_information(profile):
            checklist = build_checklist(profile, candidates, [q.question for q in questions], llm_provider=llm_provider)

        # Evidence backing this turn's citations is every evidence chunk
        # across every candidate — flattened, de-duplicated by chunk_id, in
        # the same RetrievedChunk shape Phase 5 citations have always used.
        retrieved_chunks: list[RetrievedChunk] = []
        seen_chunk_ids: set[str] = set()
        for candidate in candidates:
            for chunk in candidate.evidence:
                if chunk.chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk.chunk_id)
                    retrieved_chunks.append(chunk)

        context_block = build_discovery_context_block(profile, questions, candidates, checklist)
        language_instruction = build_language_instruction(language or DEFAULT_LANGUAGE)
        system_prompt = f"{DISCOVERY_SYSTEM_PROMPT}\n\n{context_block}\n\n{language_instruction}"

        history_pairs = [(m.role, m.content) for m in conversation.messages if m.id != user_message.id]
        history_pairs = truncate_history(history_pairs)
        conversation_history = [LLMMessage(role=role, content=content) for role, content in history_pairs]

        llm_response = self._generate(llm_provider, system_prompt, conversation_history, user_text, conversation.id)

        # --- Safety filter (Phase 10) ---
        # Live testing against a real local model showed prompt wording
        # alone is not a reliable guardrail: a 7B model fabricated IS
        # standard numbers and an invented applicability status word even
        # under an explicit "do not do this" system prompt. This is the
        # hard guarantee the prompt could not provide — see
        # app/product/response_safety.py's module docstring for the full
        # story. A response that mentions any standard number not actually
        # present in this turn's retrieved evidence is discarded and
        # replaced with a templated, zero-LLM-prose fallback built directly
        # from the structured candidates/questions.
        checklist_requirements = checklist.items if checklist else []
        safety_result = check_response_safety(llm_response.content, candidates, checklist_requirements, profile=profile)
        if not safety_result.is_safe:
            logger.warning(
                "conversation=%s discovery response rejected — fabricated standard numbers: %s, "
                "fabricated mandatory claim: %s, fabricated checklist items: %s, "
                "fabricated profile resolution: %s",
                conversation.id,
                safety_result.fabricated_standard_numbers,
                safety_result.fabricated_mandatory_claim,
                safety_result.fabricated_checklist_items,
                safety_result.fabricated_profile_resolution,
            )
            llm_response = LLMResponse(
                content=build_fallback_response(questions, candidates, requirements=checklist_requirements or None),
                model=llm_response.model,
                provider=llm_response.provider,
            )

        assistant_message, citation_responses = self._persist_assistant_response(conversation, llm_response, retrieved_chunks)

        return ChatResponse(
            conversation_id=conversation.id,
            message=MessageResponse(
                id=assistant_message.id,
                role=assistant_message.role,
                content=assistant_message.content,
                timestamp=assistant_message.created_at,
                citations=citation_responses,
            ),
            product_profile=ProductProfileResponse(
                product_name=profile.product_name,
                product_category=profile.product_category,
                product_type=profile.product_type,
                intended_use=profile.intended_use,
                target_market=profile.target_market,
                manufacturing_location=profile.manufacturing_location,
                electrical_characteristics=profile.electrical_characteristics,
                capacity=profile.capacity,
                materials=profile.materials,
                technology=profile.technology,
                application=profile.application,
                other_attributes=profile.other_attributes,
            ),
            clarification_questions=[q.question for q in questions],
            candidate_standards=candidates,
            compliance_checklist=checklist,
        )

    def _generate(
        self,
        llm_provider: LLMProvider,
        system_prompt: str,
        conversation_history: list[LLMMessage],
        user_text: str,
        conversation_id: str,
    ):
        """Calls the configured LLM provider and maps its exceptions to the
        API error-code contract. Returns the raw LLMResponse — shared by
        both the plain BIS chat path and the Phase 10 discovery path."""
        llm_start = time.monotonic()
        try:
            llm_response = llm_provider.generate(
                system_prompt=system_prompt, conversation_history=conversation_history, user_message=user_text
            )
        except OllamaNotRunningError as exc:
            logger.warning("Ollama not reachable for conversation %s: %s", conversation_id, exc)
            raise ChatGenerationError("OLLAMA_NOT_RUNNING", str(exc)) from exc
        except OllamaModelNotFoundError as exc:
            logger.warning("Ollama model not found for conversation %s: %s", conversation_id, exc)
            raise ChatGenerationError("OLLAMA_MODEL_NOT_FOUND", str(exc)) from exc
        except LLMProviderError as exc:
            logger.warning("LLM provider %s failed for conversation %s: %s", llm_provider.name, conversation_id, exc)
            raise ChatGenerationError("LLM_PROVIDER_ERROR", f"LLM provider failed: {exc}") from exc
        llm_duration_ms = (time.monotonic() - llm_start) * 1000
        logger.info(
            "conversation=%s provider=%s model=%s duration=%.1fms",
            conversation_id,
            llm_response.provider,
            llm_response.model,
            llm_duration_ms,
        )
        return llm_response

    def _persist_assistant_response(
        self, conversation: Conversation, llm_response, retrieved_chunks: list[RetrievedChunk]
    ) -> tuple[Message, list[CitationResponse]]:
        """Persists the assistant's reply and citations built directly from
        RetrievedChunk objects — never from the LLM's own output. Shared by
        both the plain BIS chat path and the Phase 10 discovery path, so
        this guarantee holds identically in both modes."""
        assistant_message = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            role=MessageRole.assistant.value,
            content=llm_response.content,
        )
        self.messages.create(assistant_message)

        citation_responses: list[CitationResponse] = []
        for chunk in retrieved_chunks:
            citation = MessageCitation(
                message_id=assistant_message.id,
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                page_number=chunk.page_number,
                section=chunk.section,
                chunk_id=chunk.chunk_id,
                similarity_score=chunk.similarity_score,
            )
            self.citations.add(citation)
            citation_responses.append(
                CitationResponse(
                    document_id=chunk.document_id,
                    document_name=chunk.document_name,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    chunk_id=chunk.chunk_id,
                )
            )

        conversation.updated_at = datetime.now(timezone.utc)
        self.conversations.touch(conversation)
        return assistant_message, citation_responses

    def _get_or_create_conversation(
        self, user_text: str, conversation_id: str | None, user_id: str | None
    ) -> Conversation:
        if conversation_id:
            existing = self.conversations.get_by_id(conversation_id)
            # Treated as "not found" (not a 403) both when the
            # conversation genuinely doesn't exist and when it belongs to
            # a different owner — same reasoning as
            # HistoryService._get_owned_conversation: a caller with no
            # right to this conversation should not be able to
            # distinguish "wrong ID" from "someone else's ID" by response
            # shape, and it must be impossible to append messages to
            # another user's (or another anonymous session's) chat just
            # by knowing its id.
            if not existing or existing.user_id != user_id:
                raise ChatNotFoundError(conversation_id)
            return existing

        conversation = Conversation(id=str(uuid.uuid4()), title=_derive_title(user_text), user_id=user_id)
        return self.conversations.create(conversation)
