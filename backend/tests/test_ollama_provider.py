"""
OllamaLLMProvider tests — Phase 7.

All HTTP calls to Ollama are mocked (via monkeypatching httpx.post) so this
suite never requires a running Ollama instance. Live local inference is
verified separately and documented outside the automated test suite (see
docs/CHAT_RAG.md / the Phase 7 handoff) — never claimed here.
"""

import httpx
import pytest

from app.llm.ollama_provider import OllamaLLMProvider
from app.llm.provider import LLMMessage, LLMProviderError, OllamaModelNotFoundError, OllamaNotRunningError


class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text or (str(json_body) if json_body is not None else "")

    def json(self):
        if self._json_body is None:
            raise ValueError("no json body")
        return self._json_body


# --- Configuration ---


def test_ollama_provider_uses_configured_base_url_and_model():
    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    assert provider.name == "ollama"
    assert provider.model == "qwen2.5:7b"
    assert provider.is_mock is False


def test_ollama_provider_strips_trailing_slash_from_base_url():
    provider = OllamaLLMProvider(base_url="http://localhost:11434/", model="qwen2.5:7b")
    assert provider._base_url == "http://localhost:11434"


# --- Request construction ---


def test_ollama_provider_posts_to_chat_endpoint_with_correct_model(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(200, {"message": {"content": "hello"}})

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    provider.generate(system_prompt="sys", conversation_history=[], user_message="hi")

    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["json"]["model"] == "qwen2.5:7b"
    assert captured["json"]["stream"] is False


def test_ollama_provider_sets_num_ctx_to_avoid_silent_truncation(monkeypatch):
    """Ollama's server default num_ctx (2048) is too small for a grounded
    prompt (rules + evidence + language instruction) and silently truncates
    the response mid-sentence instead of erroring — discovered during Phase
    7 live verification. The provider must always request a larger context
    window explicitly."""
    captured = {}

    def fake_post(url, json, timeout):
        captured["json"] = json
        return _FakeResponse(200, {"message": {"content": "hello"}})

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    provider.generate(system_prompt="sys", conversation_history=[], user_message="hi")

    assert captured["json"]["options"]["num_ctx"] >= 8192


def test_ollama_provider_separates_system_history_and_user_message(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["messages"] = json["messages"]
        return _FakeResponse(200, {"message": {"content": "hello"}})

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    history = [LLMMessage(role="user", content="earlier question"), LLMMessage(role="assistant", content="earlier answer")]
    provider.generate(system_prompt="SYSTEM INSTRUCTIONS", conversation_history=history, user_message="new question")

    messages = captured["messages"]
    assert messages[0] == {"role": "system", "content": "SYSTEM INSTRUCTIONS"}
    assert messages[1] == {"role": "user", "content": "earlier question"}
    assert messages[2] == {"role": "assistant", "content": "earlier answer"}
    assert messages[-1] == {"role": "user", "content": "new question"}


def test_ollama_provider_includes_hindi_language_instruction_in_system_message(monkeypatch):
    """The language instruction (built by grounding.build_language_instruction)
    is just part of the system_prompt string the caller passes in — this
    confirms the provider forwards it verbatim as the system message,
    without ever touching or reparsing it."""
    captured = {}

    def fake_post(url, json, timeout):
        captured["messages"] = json["messages"]
        return _FakeResponse(200, {"message": {"content": "hello"}})

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    system_prompt = "GROUNDING RULES...\n\nRESPONSE LANGUAGE: Answer in Hindi (hi)."
    provider.generate(system_prompt=system_prompt, conversation_history=[], user_message="question")

    assert captured["messages"][0]["content"] == system_prompt
    assert "Hindi" in captured["messages"][0]["content"]


# --- Response parsing ---


def test_ollama_provider_returns_content_from_message_field(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: _FakeResponse(200, {"message": {"content": "  the answer  "}}))

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    result = provider.generate(system_prompt="sys", conversation_history=[], user_message="hi")

    assert result.content == "the answer"
    assert result.model == "qwen2.5:7b"
    assert result.provider == "ollama"


def test_ollama_provider_raises_on_empty_response(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: _FakeResponse(200, {"message": {"content": "   "}}))

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    with pytest.raises(LLMProviderError):
        provider.generate(system_prompt="sys", conversation_history=[], user_message="hi")


def test_ollama_provider_raises_on_malformed_response(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: _FakeResponse(200, {"unexpected": "shape"}))

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    with pytest.raises(LLMProviderError):
        provider.generate(system_prompt="sys", conversation_history=[], user_message="hi")


# --- Error handling ---


def test_ollama_provider_raises_not_running_error_on_connect_error(monkeypatch):
    def fake_post(url, json, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    with pytest.raises(OllamaNotRunningError):
        provider.generate(system_prompt="sys", conversation_history=[], user_message="hi")


def test_ollama_provider_raises_model_not_found_error_on_404(monkeypatch):
    monkeypatch.setattr(
        httpx, "post", lambda url, json, timeout: _FakeResponse(404, {"error": "model 'nope' not found"})
    )

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="nope")
    with pytest.raises(OllamaModelNotFoundError):
        provider.generate(system_prompt="sys", conversation_history=[], user_message="hi")


def test_ollama_provider_raises_generic_provider_error_on_timeout(monkeypatch):
    def fake_post(url, json, timeout):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    with pytest.raises(LLMProviderError):
        provider.generate(system_prompt="sys", conversation_history=[], user_message="hi")


def test_ollama_provider_raises_generic_provider_error_on_other_http_status(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: _FakeResponse(500, text="internal server error"))

    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    with pytest.raises(LLMProviderError):
        provider.generate(system_prompt="sys", conversation_history=[], user_message="hi")


# --- get_llm_provider() selection ---


def test_get_llm_provider_selects_ollama(monkeypatch):
    from app.core.config import get_settings
    from app.llm.provider import get_llm_provider

    get_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        provider = get_llm_provider()
        assert isinstance(provider, OllamaLLMProvider)
        assert provider.model == "qwen2.5:7b"
        assert provider._base_url == "http://localhost:11434"
    finally:
        get_settings.cache_clear()


def test_get_llm_provider_ollama_defaults_model_when_unset(monkeypatch):
    from app.core.config import get_settings
    from app.llm.provider import get_llm_provider

    get_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    try:
        provider = get_llm_provider()
        assert isinstance(provider, OllamaLLMProvider)
        assert provider.model == "qwen2.5:3b"
    finally:
        get_settings.cache_clear()
