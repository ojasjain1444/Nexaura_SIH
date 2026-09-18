from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_response_shape():
    response = client.get("/api/health")
    body = response.json()
    assert set(body.keys()) == {"status", "service", "environment"}
    assert body["status"] == "ok"


def test_health_reports_correct_service_name():
    response = client.get("/api/health")
    body = response.json()
    assert body["service"] == "bis-sahayak-api"


def test_health_does_not_leak_secrets():
    response = client.get("/api/health")
    body_text = response.text.lower()
    forbidden_substrings = ["api_key", "password", "secret", "database_url", "sqlite:///", "postgresql://"]
    for forbidden in forbidden_substrings:
        assert forbidden not in body_text, f"health response leaked '{forbidden}'"
