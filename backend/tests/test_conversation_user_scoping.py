"""
Conversation user-scoping — verifies real per-user isolation now that
accounts exist (see app.models.conversation and
app.services.history_service._get_owned_conversation). The anonymous
(no-token) path is exercised throughout the rest of the test suite
already; these tests are specifically about the ownership boundary a
logged-in user introduces.
"""

import pytest


@pytest.fixture(autouse=True)
def isolated_llm_provider(monkeypatch):
    """These tests only need chat_service to create/find conversations —
    not real LLM generation — but /api/chat still requires a configured
    provider to reach that far. The mock provider is enough."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")


def _register(client, username: str, pin: str = "12") -> str:
    response = client.post("/api/auth/register", json={"username": username, "pin": pin})
    return response.json()["token"]


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_logged_in_users_conversation_appears_in_their_own_history(client):
    token = _register(client, "owner1")
    chat_response = client.post("/api/chat", json={"message": "hello"}, headers=_auth_header(token))
    assert chat_response.status_code == 200

    history = client.get("/api/history", headers=_auth_header(token)).json()
    assert len(history) == 1


def test_second_user_does_not_see_first_users_conversation(client):
    token_a = _register(client, "owner2a")
    token_b = _register(client, "owner2b")

    client.post("/api/chat", json={"message": "hello from A"}, headers=_auth_header(token_a))

    history_b = client.get("/api/history", headers=_auth_header(token_b)).json()
    assert history_b == []


def test_anonymous_history_excludes_logged_in_users_conversations(client):
    token = _register(client, "owner3")
    client.post("/api/chat", json={"message": "hello"}, headers=_auth_header(token))

    anonymous_history = client.get("/api/history").json()
    assert anonymous_history == []


def test_second_user_cannot_read_first_users_conversation_by_id(client):
    token_a = _register(client, "owner4a")
    token_b = _register(client, "owner4b")

    conversation_id = client.post("/api/chat", json={"message": "hello"}, headers=_auth_header(token_a)).json()[
        "conversationId"
    ]

    response = client.get(f"/api/history/{conversation_id}", headers=_auth_header(token_b))
    assert response.status_code == 404


def test_second_user_cannot_send_a_message_into_first_users_conversation(client):
    token_a = _register(client, "owner5a")
    token_b = _register(client, "owner5b")

    conversation_id = client.post("/api/chat", json={"message": "hello"}, headers=_auth_header(token_a)).json()[
        "conversationId"
    ]

    response = client.post(
        "/api/chat",
        json={"message": "hijack attempt", "conversationId": conversation_id},
        headers=_auth_header(token_b),
    )
    assert response.status_code == 404


def test_second_user_cannot_delete_first_users_conversation(client):
    token_a = _register(client, "owner6a")
    token_b = _register(client, "owner6b")

    conversation_id = client.post("/api/chat", json={"message": "hello"}, headers=_auth_header(token_a)).json()[
        "conversationId"
    ]

    response = client.delete(f"/api/history/{conversation_id}", headers=_auth_header(token_b))
    assert response.status_code == 404

    # Still there for its real owner — the failed delete attempt must not
    # have removed it.
    owned_response = client.get(f"/api/history/{conversation_id}", headers=_auth_header(token_a))
    assert owned_response.status_code == 200


def test_anonymous_caller_cannot_access_a_logged_in_users_conversation(client):
    token = _register(client, "owner7")
    conversation_id = client.post("/api/chat", json={"message": "hello"}, headers=_auth_header(token)).json()[
        "conversationId"
    ]

    response = client.get(f"/api/history/{conversation_id}")
    assert response.status_code == 404


def test_logged_in_user_cannot_continue_an_anonymous_conversation(client):
    anonymous_conversation_id = client.post("/api/chat", json={"message": "anonymous hello"}).json()["conversationId"]

    token = _register(client, "owner8")
    response = client.post(
        "/api/chat",
        json={"message": "trying to join anonymous chat", "conversationId": anonymous_conversation_id},
        headers=_auth_header(token),
    )
    assert response.status_code == 404
