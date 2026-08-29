"""Tests for the health endpoint."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_endpoint_returns_expected_fields() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["service"] == "Urban Heat Intelligence API"
    assert payload["version"] == "0.1.0"
    assert isinstance(payload["fortyguard_api_configured"], bool)


def test_root_endpoint() -> None:
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "Urban Heat Intelligence API"
    assert payload["health"] == "/api/v1/health"
