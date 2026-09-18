def test_register_creates_user_and_returns_session_token(client):
    response = client.post("/api/auth/register", json={"username": "alice", "pin": "42"})
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["username"] == "alice"
    assert body["token"]


def test_register_rejects_duplicate_username(client):
    client.post("/api/auth/register", json={"username": "bob", "pin": "12"})
    response = client.post("/api/auth/register", json={"username": "bob", "pin": "34"})
    assert response.status_code == 409


def test_register_rejects_non_two_digit_pin(client):
    response = client.post("/api/auth/register", json={"username": "carol", "pin": "1234"})
    assert response.status_code == 422

    response = client.post("/api/auth/register", json={"username": "carol", "pin": "ab"})
    assert response.status_code == 422


def test_login_with_correct_pin_succeeds(client):
    client.post("/api/auth/register", json={"username": "dave", "pin": "55"})
    response = client.post("/api/auth/login", json={"username": "dave", "pin": "55"})
    assert response.status_code == 200
    assert response.json()["user"]["username"] == "dave"


def test_login_with_wrong_pin_fails(client):
    client.post("/api/auth/register", json={"username": "erin", "pin": "55"})
    response = client.post("/api/auth/login", json={"username": "erin", "pin": "99"})
    assert response.status_code == 401


def test_login_with_unknown_username_fails(client):
    response = client.post("/api/auth/login", json={"username": "nobody", "pin": "00"})
    assert response.status_code == 401


def test_me_requires_valid_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401

    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_returns_current_user_for_valid_token(client):
    register_response = client.post("/api/auth/register", json={"username": "frank", "pin": "07"})
    token = register_response.json()["token"]

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "frank"


def test_logout_invalidates_the_session(client):
    register_response = client.post("/api/auth/register", json={"username": "grace", "pin": "18"})
    token = register_response.json()["token"]

    logout_response = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_response.status_code == 204

    me_response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 401


def test_two_users_get_different_sessions(client):
    token_a = client.post("/api/auth/register", json={"username": "heidi", "pin": "01"}).json()["token"]
    token_b = client.post("/api/auth/register", json={"username": "ivan", "pin": "02"}).json()["token"]

    response_a = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    response_b = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_b}"})

    assert response_a.json()["username"] == "heidi"
    assert response_b.json()["username"] == "ivan"
