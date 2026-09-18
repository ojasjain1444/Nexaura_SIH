"""
MockLLMProvider — MOCK / DEVELOPMENT ONLY.

This is NOT a real AI model. It exists so the chat pipeline (retrieval,
context construction, citation generation, persistence) can be developed
and tested end-to-end without requiring a real LLM API key, and so
automated tests never depend on an external API or incur real costs.

It must never be silently substituted for a real provider — it only
activates when LLM_PROVIDER=mock is explicitly set. Every response it
produces is prefixed to make it unmistakable in logs/UI during development
that no real generation occurred.

Phase 6: it does not perform real translation (it is a mock — it never
claims real generation of any kind), but it does detect the language
instruction that app/llm/grounding.py's build_language_instruction()
appends to the system prompt and reflects the requested language back
explicitly, so automated tests can verify the language selection actually
reached the provider without needing a real LLM.
"""

import re

from app.llm.provider import LLMMessage, LLMResponse

MOCK_LABEL = "[MOCK LLM — DEVELOPMENT ONLY, NOT A REAL AI RESPONSE]"

_LANGUAGE_INSTRUCTION_RE = re.compile(r"RESPONSE LANGUAGE: Answer in (\w+) \((\w+)\)")


class MockLLMProvider:
    name = "mock"
    model = "mock-echo-v1"
    is_mock = True

    def generate(self, system_prompt: str, conversation_history: list[LLMMessage], user_message: str) -> LLMResponse:
        # Deterministic, inspectable behavior: summarizes what it was given
        # rather than pretending to reason about it — useful for verifying
        # the context actually reached this point, without claiming any
        # real understanding.
        history_count = len(conversation_history)
        match = _LANGUAGE_INSTRUCTION_RE.search(system_prompt)
        language_label = f"{match.group(1).upper()} ({match.group(2)})" if match else "ENGLISH (en)"
        content = (
            f"{MOCK_LABEL}\n"
            f"[MOCK RESPONSE LANGUAGE: {language_label}]\n"
            f"Received {history_count} prior message(s) and this query: \"{user_message}\"\n"
            f"System prompt length: {len(system_prompt)} characters."
        )
        return LLMResponse(content=content, model=self.model, provider=self.name)
