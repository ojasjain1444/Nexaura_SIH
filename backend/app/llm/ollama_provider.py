"""
OllamaLLMProvider — real LLM generation via a locally running Ollama
server (Phase 7). No API key involved: Ollama runs on the developer's own
machine, so "configured" only means OLLAMA_BASE_URL points at a reachable
server and LLM_MODEL names a model that has been pulled locally.

Uses httpx (already a project dependency, no new package required) to call
Ollama's /api/chat endpoint directly rather than any SDK, since Ollama's
HTTP API is small and stable.
"""

import httpx

from app.llm.provider import LLMMessage, LLMProviderError, LLMResponse, OllamaModelNotFoundError, OllamaNotRunningError

DEFAULT_TIMEOUT_SECONDS = 120.0

# Ollama's server-side default num_ctx is only 2048 tokens. Our grounded
# system prompt (grounding rules + retrieved evidence block + language
# instruction) can alone approach or exceed that, which silently truncates
# the response mid-sentence instead of erroring — discovered during Phase 7
# live verification with qwen2.5:7b. 8192 comfortably fits prompt + a full
# reply for this model without a large extra memory cost.
DEFAULT_NUM_CTX = 8192

# Generation is the whole cost of a reply: warm retrieval is ~0.09s while
# the model takes ~9s to produce ~800 characters on CPU, and the tail of a
# long answer is where it drifts into restating the evidence. Capping the
# reply keeps answers to the part that is actually grounded and makes the
# app usable interactively. num_predict is a ceiling, not a target — short
# answers still finish early and return immediately.
DEFAULT_NUM_PREDICT = 400


class OllamaLLMProvider:
    is_mock = False

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        num_ctx: int = DEFAULT_NUM_CTX,
        num_predict: int = DEFAULT_NUM_PREDICT,
    ):
        self.name = "ollama"
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._num_ctx = num_ctx
        self._num_predict = num_predict

    def generate(self, system_prompt: str, conversation_history: list[LLMMessage], user_message: str) -> LLMResponse:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend({"role": m.role, "content": m.content} for m in conversation_history)
        messages.append({"role": "user", "content": user_message})

        try:
            response = httpx.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_ctx": self._num_ctx,
                        "num_predict": self._num_predict,
                        # Grounded Q&A wants the evidence restated faithfully,
                        # not paraphrased creatively. The default (0.8) is
                        # what lets the model embellish past what it was given.
                        "temperature": 0.1,
                    },
                },
                timeout=self._timeout,
            )
        except httpx.ConnectError as exc:
            raise OllamaNotRunningError(
                f"Could not reach Ollama at {self._base_url}. Is `ollama serve` running?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMProviderError(f"Ollama request to {self._base_url} timed out.") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Ollama request failed: {exc}") from exc

        if response.status_code == 404:
            raise OllamaModelNotFoundError(
                f"Model '{self.model}' was not found on the Ollama server at {self._base_url}. "
                f"Run `ollama pull {self.model}` first."
            )
        if response.status_code != 200:
            raise LLMProviderError(f"Ollama returned HTTP {response.status_code}: {response.text}")

        try:
            body = response.json()
            content = body["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMProviderError(f"Ollama returned an unexpected response shape: {response.text}") from exc

        content = content.strip()
        if not content:
            raise LLMProviderError("Ollama returned an empty response.")

        return LLMResponse(content=content, model=self.model, provider=self.name)
