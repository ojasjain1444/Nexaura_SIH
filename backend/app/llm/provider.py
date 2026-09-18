"""
LLM provider abstraction.

Nothing outside this module (ChatService, the API route, etc.) imports a
specific LLM SDK directly — everything talks to the `LLMProvider` protocol,
so swapping providers is a configuration change (`LLM_PROVIDER` env var),
never a code change to the chat pipeline.

Provider selection (see get_llm_provider() below):
  - No LLM_PROVIDER configured at all -> LLMNotConfiguredError. The
    backend still starts and every other endpoint still works; only chat
    generation is unavailable until a provider is configured.
  - LLM_PROVIDER=mock -> MockLLMProvider. Explicit opt-in, clearly labelled
    MOCK/DEVELOPMENT ONLY in every place it surfaces (logs, responses).
    Never silently substituted for a real provider on failure.
  - LLM_PROVIDER=anthropic -> AnthropicLLMProvider (requires
    LLM_API_KEY). A real, paid cloud provider — kept available but never
    the default, per Phase 7's local-first direction.
  - LLM_PROVIDER=ollama -> OllamaLLMProvider (Phase 7). Talks to a locally
    running Ollama server (OLLAMA_BASE_URL, default
    http://localhost:11434) — no API key needed. This is the local/
    open-source path; still opt-in via LLM_PROVIDER, never auto-selected.
"""

from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings


@dataclass
class LLMMessage:
    role: str  # "user" or "assistant" — conversation history only, never "system"
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str


class LLMProviderError(Exception):
    """A configured provider failed to generate a response (network error,
    API error, rate limit, etc.) — distinct from LLMNotConfiguredError."""


class LLMNotConfiguredError(Exception):
    """No usable LLM provider is configured. The caller must return a
    structured LLM_NOT_CONFIGURED error to the client, never a fabricated
    answer."""


class OllamaNotRunningError(LLMProviderError):
    """The Ollama server at OLLAMA_BASE_URL could not be reached (connection
    refused/timeout) — distinct from a model-not-found error so the API can
    return a more actionable message."""


class OllamaModelNotFoundError(LLMProviderError):
    """Ollama is running but the configured model is not pulled locally."""


class LLMProvider(Protocol):
    name: str
    model: str
    is_mock: bool

    def generate(self, system_prompt: str, conversation_history: list[LLMMessage], user_message: str) -> LLMResponse: ...


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    provider_name = settings.llm_provider

    if not provider_name:
        raise LLMNotConfiguredError("LLM_PROVIDER is not set. Real chat generation is unavailable until configured.")

    if provider_name == "mock":
        from app.llm.mock_provider import MockLLMProvider

        return MockLLMProvider()

    if provider_name == "anthropic":
        if not settings.llm_api_key:
            raise LLMNotConfiguredError("LLM_PROVIDER=anthropic but LLM_API_KEY is not set.")
        from app.llm.anthropic_provider import AnthropicLLMProvider

        return AnthropicLLMProvider(api_key=settings.llm_api_key, model=settings.llm_model or "claude-sonnet-4-5")

    if provider_name == "ollama":
        from app.llm.ollama_provider import OllamaLLMProvider

        # 3b over 7b: measured ~2-3x faster on this machine (an answer in
        # ~3s rather than ~10s) with no loss of grounding quality — it
        # declines off-corpus questions more crisply and cites clauses just
        # as accurately. Generation is the entire cost of a reply here, so
        # model size is the main lever on responsiveness.
        return OllamaLLMProvider(base_url=settings.ollama_base_url, model=settings.llm_model or "qwen2.5:3b")

    raise LLMNotConfiguredError(f"Unknown LLM_PROVIDER '{provider_name}'. Supported: 'mock', 'anthropic', 'ollama'.")
