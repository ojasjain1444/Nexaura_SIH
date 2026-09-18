"""
API schemas for chat/conversation persistence, matching src/types/chat.ts's
ChatMessage / ChatSession field names.

Phase 5 adds `citations` — populated only for assistant messages generated
with real retrieval evidence.

Phase 6 adds response-language selection. `language` selects the language
of the generated answer only — it never affects retrieval, which always
runs against the stored (English/source) document text; see
app/services/chat_service.py and app/llm/grounding.py. `standard_id`
genuinely filters retrieval, per the real Standard->StandardDocument
relationship.

Phase 10 adds `mode="product_discovery"` — an explicit opt-in on
ChatRequest so existing callers (plain BIS Q&A chat) are completely
unaffected unless they ask for the new flow. Once a conversation's first
message sets mode="product_discovery", ChatService creates a ProductProfile
for that conversation and subsequent messages continue in discovery mode
automatically (the profile is looked up by conversation_id, not re-sent by
the client every turn) — matching "the profile should evolve as the
conversation continues" without requiring the frontend to track and resend
a mode flag on every message.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.candidate_standard import CandidateStandard
from app.schemas.compliance import ComplianceChecklist
from app.schemas.product_profile import ProductProfileResponse

MAX_MESSAGE_LENGTH = 4000

# Deliberately limited and explicit rather than claiming broad multilingual
# support — see docs/CHAT_RAG.md. Extend only when a concrete requirement
# justifies adding a language.
SUPPORTED_LANGUAGES = {"en": "English", "hi": "Hindi"}
DEFAULT_LANGUAGE = "en"

CHAT_MODE_PRODUCT_DISCOVERY = "product_discovery"
SUPPORTED_CHAT_MODES = {CHAT_MODE_PRODUCT_DISCOVERY}


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = Field(default=None, alias="conversationId")
    language: str | None = None
    standard_id: str | None = Field(default=None, alias="standardId")
    mode: str | None = None

    model_config = {"populate_by_name": True}

    @field_validator("message")
    @classmethod
    def message_must_be_reasonable(cls, value: str) -> str:
        if len(value) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"message must not exceed {MAX_MESSAGE_LENGTH} characters")
        return value

    @field_validator("language")
    @classmethod
    def language_must_be_supported(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
            raise ValueError(f"Unsupported language '{value}'. Supported languages: {supported}")
        return value

    @field_validator("mode")
    @classmethod
    def mode_must_be_supported(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_CHAT_MODES:
            supported = ", ".join(sorted(SUPPORTED_CHAT_MODES))
            raise ValueError(f"Unsupported mode '{value}'. Supported modes: {supported}")
        return value


class CitationResponse(BaseModel):
    document_id: str = Field(serialization_alias="documentId")
    document_name: str = Field(serialization_alias="documentName")
    page_number: int = Field(serialization_alias="pageNumber")
    section: str | None
    chunk_id: str = Field(serialization_alias="chunkId")


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    timestamp: datetime
    citations: list[CitationResponse] = Field(default_factory=list)


class ChatResponse(BaseModel):
    conversation_id: str = Field(serialization_alias="conversationId")
    message: MessageResponse
    # Phase 10 — only populated when this conversation is in product-
    # discovery mode. None for ordinary BIS Q&A chat, preserving the exact
    # existing response shape for every pre-Phase-10 caller.
    product_profile: ProductProfileResponse | None = Field(default=None, serialization_alias="productProfile")
    clarification_questions: list[str] = Field(default_factory=list, serialization_alias="clarificationQuestions")
    candidate_standards: list[CandidateStandard] = Field(default_factory=list, serialization_alias="candidateStandards")
    # Phase 11 — only populated once product-discovery has gathered enough
    # information (has_sufficient_information()) to assemble an
    # evidence-backed compliance plan. None until then, and None for every
    # non-discovery chat call, exactly like the Phase 10 fields above.
    compliance_checklist: ComplianceChecklist | None = Field(default=None, serialization_alias="complianceChecklist")


class ConversationSummaryResponse(BaseModel):
    id: str
    title: str
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class ConversationDetailResponse(ConversationSummaryResponse):
    messages: list[MessageResponse]
