"""Tests for heatmap FastAPI routes with mocked FortyGuard client."""

import httpx
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.routes.heatmap import get_heatmap_service
from backend.services.heatmap_service import HeatmapService
from main import app
from tests.conftest import make_client, sample_heatmap_request, status_payload, submission_payload

client = TestClient(app)

CONFIGURED_SETTINGS = Settings(
    FORTYGUARD_API_KEY="test-key",
    FORTYGUARD_BASE_URL="https://api.fortyguard.com",
)
UNCONFIGURED_SETTINGS = Settings(
    FORTYGUARD_API_KEY="",
    FORTYGUARD_BASE_URL="https://api.fortyguard.com",
)


def test_submit_heatmap_route_returns_activity_id() -> None:
    mock_client = make_client(
        lambda _: httpx.Response(200, json=submission_payload("route-id-1"))
    )
    service = HeatmapService(client=mock_client, settings=CONFIGURED_SETTINGS)

    app.dependency_overrides[get_heatmap_service] = lambda: service
    try:
        response = client.post(
            "/api/v1/heatmap/",
            json=sample_heatmap_request().model_dump(),
        )
    finally:
        app.dependency_overrides.clear()
        mock_client.close()

    assert response.status_code == 200
    assert response.json() == {
        "activity_id": "route-id-1",
        "message": "Heatmap submitted successfully",
    }


def test_submit_heatmap_route_maps_client_errors() -> None:
    mock_client = make_client(
        lambda _: httpx.Response(404, json={"message": "Not found"})
    )
    service = HeatmapService(client=mock_client, settings=CONFIGURED_SETTINGS)

    app.dependency_overrides[get_heatmap_service] = lambda: service
    try:
        response = client.post(
            "/api/v1/heatmap/",
            json=sample_heatmap_request().model_dump(),
        )
    finally:
        app.dependency_overrides.clear()
        mock_client.close()

    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"


def test_submit_heatmap_route_missing_api_key() -> None:
    mock_client = make_client(
        lambda _: httpx.Response(200, json=submission_payload()),
        api_key="",
    )
    service = HeatmapService(client=mock_client, settings=UNCONFIGURED_SETTINGS)

    app.dependency_overrides[get_heatmap_service] = lambda: service
    try:
        response = client.post(
            "/api/v1/heatmap/",
            json=sample_heatmap_request().model_dump(),
        )
    finally:
        app.dependency_overrides.clear()
        mock_client.close()

    assert response.status_code == 401
    assert "not configured" in response.json()["detail"].lower()


def test_submit_heatmap_route_rejects_invalid_request() -> None:
    response = client.post(
        "/api/v1/heatmap/",
        json={"polygon_aoi": {}, "date_time": {}, "granularity": "invalid"},
    )

    assert response.status_code == 422


def test_status_route_returns_processing_status() -> None:
    mock_client = make_client(
        lambda _: httpx.Response(200, json=status_payload(status="Processing"))
    )
    service = HeatmapService(client=mock_client, settings=CONFIGURED_SETTINGS)

    app.dependency_overrides[get_heatmap_service] = lambda: service
    try:
        response = client.get("/api/v1/heatmap/status/activity-123")
    finally:
        app.dependency_overrides.clear()
        mock_client.close()

    assert response.status_code == 200
    assert response.json()["status"] == "Processing"


def test_status_route_maps_downstream_error() -> None:
    mock_client = make_client(
        lambda _: httpx.Response(500, json={"message": "Server error"})
    )
    service = HeatmapService(client=mock_client, settings=CONFIGURED_SETTINGS)

    app.dependency_overrides[get_heatmap_service] = lambda: service
    try:
        response = client.get("/api/v1/heatmap/status/activity-123")
    finally:
        app.dependency_overrides.clear()
        mock_client.close()

    assert response.status_code == 500
    assert response.json()["detail"] == "Server error"


def test_poll_route_returns_completed_status() -> None:
    responses = [
        httpx.Response(200, json=status_payload(status="Processing")),
        httpx.Response(200, json=status_payload(status="Completed")),
    ]
    mock_client = make_client(lambda _: responses.pop(0))
    service = HeatmapService(client=mock_client, settings=CONFIGURED_SETTINGS)

    app.dependency_overrides[get_heatmap_service] = lambda: service
    try:
        response = client.get(
            "/api/v1/heatmap/status/activity-123/poll",
            params={"max_attempts": 2, "poll_interval_seconds": 0},
        )
    finally:
        app.dependency_overrides.clear()
        mock_client.close()

    assert response.status_code == 200
    assert response.json()["status"] == "Completed"
