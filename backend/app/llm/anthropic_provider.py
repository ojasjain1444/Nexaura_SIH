"""
AnthropicLLMProvider — real LLM generation via the Anthropic Messages API.

Status as of Phase 5: implemented but NOT tested with a real API key — no
LLM_API_KEY was configured in this development environment (verified: no
.env file exists, no LLM_* environment variables are set). This class is
written to work correctly once a real key is provided; until then, no
claim is made that it has actually generated a real response.
"""

from app.llm.provider import LLMMessage, LLMProviderError, LLMResponse


class AnthropicLLMProvider:
    is_mock = False

    def __init__(self, api_key: str, model: str):
        self.name = "anthropic"
        self.model = model
        self._api_key = api_key

    def generate(self, system_prompt: str, conversation_history: list[LLMMessage], user_message: str) -> LLMResponse:
        try:
            import anthropic
        except ImportError as exc:
            raise LLMProviderError("The 'anthropic' package is not installed. Run `pip install -r requirements.txt`.") from exc

        client = anthropic.Anthropic(api_key=self._api_key)

        messages = [{"role": m.role, "content": m.content} for m in conversation_history]
        messages.append({"role": "user", "content": user_message})

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=messages,
            )
        except anthropic.APIError as exc:
            raise LLMProviderError(f"Anthropic API error: {exc}") from exc
        except Exception as exc:
            raise LLMProviderError(f"Anthropic request failed: {exc}") from exc

        text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        content = "".join(text_blocks).strip()
        if not content:
            raise LLMProviderError("Anthropic returned an empty response.")

        return LLMResponse(content=content, model=self.model, provider=self.name)
