"""
backend/tests/test_api.py — Integration and endpoint test suite for Nexaura FastAPI Backend.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_root_redirect(client: TestClient):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (307, 302)
    assert response.headers["location"] == "/docs"


def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "version" in data
    assert "database_connected" in data


def test_get_stats(client: TestClient):
    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["standards_count"] > 0
    assert data["database_name"] == "nexaura"
    assert "rag_chunks_count" in data


def test_list_standards(client: TestClient):
    response = client.get("/api/v1/standards?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert len(data["items"]) <= 10
    assert "standard_number" in data["items"][0]


def test_search_standards(client: TestClient):
    response = client.get("/api/v1/standards?q=concrete")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert any("concrete" in s["title"].lower() or "concrete" in s["standard_number"].lower() for s in data["items"])


def test_get_standard_detail(client: TestClient):
    response = client.get("/api/v1/standards/IS 456:2000")
    assert response.status_code == 200
    data = response.json()
    assert "IS 456" in data["standard_number"]
    assert "title" in data
    assert data["has_pdf"] is True


def test_get_standard_pdf(client: TestClient):
    response = client.get("/api/v1/standards/IS 456:2000/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert int(response.headers["content-length"]) > 100000


def test_get_labs_for_standard(client: TestClient):
    response = client.get("/api/v1/standards/IS 456:2000/labs")
    assert response.status_code == 200
    labs = response.json()
    assert isinstance(labs, list)
    assert len(labs) > 0
    assert "lab_name" in labs[0]


def test_list_labs(client: TestClient):
    response = client.get("/api/v1/labs?page=1&page_size=5")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert len(data["items"]) <= 5


def test_rag_query(client: TestClient):
    payload = {
        "query": "concrete reinforcement strength",
        "top_k": 3,
    }
    response = client.post("/api/v1/rag/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == payload["query"]
    assert "answer" in data
    assert len(data["chunks"]) > 0
    assert len(data["cited_standards"]) > 0
