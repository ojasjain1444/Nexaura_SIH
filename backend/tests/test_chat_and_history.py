"""
Chat + history API tests.

Phase 5 changed the real contract: POST /api/chat now requires a
configured LLM provider to succeed (previously, Phase 2's keyword-matched
demo responder always "succeeded"). These tests configure the explicit
MOCK provider via monkeypatch (never a real external API call) to exercise
the full chat -> history flow, matching how the app itself only activates
mock behavior when LLM_PROVIDER=mock is explicitly set — see
tests/test_chat_rag.py for tests of the LLM_NOT_CONFIGURED path itself.
"""

import pytest

from app.llm.mock_provider import MockLLMProvider


@pytest.fixture(autouse=True)
def use_mock_llm(monkeypatch):
    monkeypatch.setattr("app.services.chat_service.get_llm_provider", lambda: MockLLMProvider())


def test_new_chat_message_creates_conversation(client):
    response = client.post("/api/chat", json={"message": "Which standard applies to packaged drinking water?"})
    assert response.status_code == 200
    body = response.json()
    assert "conversationId" in body
    assert body["message"]["role"] == "assistant"
    assert len(body["message"]["content"]) > 0


def test_followup_message_reuses_conversation(client):
    first = client.post("/api/chat", json={"message": "Which standard applies to packaged drinking water?"})
    conversation_id = first.json()["conversationId"]

    second = client.post(
        "/api/chat", json={"message": "What certification is needed?", "conversationId": conversation_id}
    )
    assert second.status_code == 200
    assert second.json()["conversationId"] == conversation_id


def test_chat_with_unknown_conversation_id_returns_404(client):
    response = client.post("/api/chat", json={"message": "hello", "conversationId": "does-not-exist"})
    assert response.status_code == 404


def test_chat_with_empty_message_returns_422(client):
    response = client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 422


def test_history_list_shows_created_conversation(client):
    response = client.post("/api/chat", json={"message": "How does gold hallmarking work?"})
    conversation_id = response.json()["conversationId"]

    history = client.get("/api/history")
    assert history.status_code == 200
    ids = [c["id"] for c in history.json()]
    assert conversation_id in ids


def test_history_detail_contains_both_messages(client):
    response = client.post("/api/chat", json={"message": "How does gold hallmarking work?"})
    conversation_id = response.json()["conversationId"]

    detail = client.get(f"/api/history/{conversation_id}")
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_history_detail_unknown_id_returns_404(client):
    response = client.get("/api/history/does-not-exist")
    assert response.status_code == 404


def test_delete_conversation_removes_it(client):
    response = client.post("/api/chat", json={"message": "test message"})
    conversation_id = response.json()["conversationId"]

    delete_response = client.delete(f"/api/history/{conversation_id}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/api/history/{conversation_id}")
    assert get_response.status_code == 404


def test_delete_nonexistent_conversation_returns_404(client):
    response = client.delete("/api/history/does-not-exist")
    assert response.status_code == 404
