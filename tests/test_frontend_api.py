"""Tests for the Streamlit-to-FastAPI client using mocked HTTP."""

import httpx
import pytest

from frontend.services.api import BackendAPIClient, BackendAPIError


def make_backend_client(handler):
    http_client = httpx.Client(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    )
    return BackendAPIClient(http_client=http_client)


def test_frontend_client_submits_only_to_fastapi() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["json"] = request.read()
        return httpx.Response(200, json={"activity_id": "frontend-1"})

    client = make_backend_client(handler)
    try:
        response = client.submit_heatmap({"polygon_aoi": {}, "date_time": {}, "granularity": 100})
    finally:
        client.close()

    assert response["activity_id"] == "frontend-1"
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/heatmap/"


def test_frontend_client_gets_status_from_fastapi() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/heatmap/status/activity-1"
        return httpx.Response(
            200,
            json={"activity_id": "activity-1", "status": "Processing"},
        )

    client = make_backend_client(handler)
    try:
        response = client.get_heatmap_status("activity-1")
    finally:
        client.close()

    assert response["status"] == "Processing"


def test_frontend_client_maps_backend_errors_without_stack_traces() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Not configured"})

    client = make_backend_client(handler)
    try:
        with pytest.raises(BackendAPIError) as exc_info:
            client.get_heatmap_status("activity-1")
    finally:
        client.close()

    assert exc_info.value.status_code == 401
    assert str(exc_info.value) == "Not configured"


def test_frontend_client_rejects_malformed_backend_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    client = make_backend_client(handler)
    try:
        with pytest.raises(BackendAPIError, match="invalid JSON"):
            client.fetch_health()
    finally:
        client.close()


def test_frontend_client_submits_heat_intelligence_to_fastapi() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(200, json={"activity_id": "fe-hi-001"})

    client = make_backend_client(handler)
    try:
        response = client.submit_heat_intelligence({
            "latitude": 40.705,
            "longitude": -74.009,
            "temperature": 32.5,
            "date": "2024-07-15",
            "analysis": ["environmental"],
        })
    finally:
        client.close()


    assert response["activity_id"] == "fe-hi-001"
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/heat-intelligence/"


def test_frontend_client_gets_heat_intelligence_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/heat-intelligence/status/hi-act-1"
        return httpx.Response(200, json={"activity_id": "hi-act-1", "status": "Processing"})

    client = make_backend_client(handler)
    try:
        response = client.get_heat_intelligence_status("hi-act-1")
    finally:
        client.close()

    assert response["status"] == "Processing"


def test_frontend_client_polls_heat_intelligence() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/heat-intelligence/status/hi-act-2/poll"
        return httpx.Response(200, json={"activity_id": "hi-act-2", "status": "Completed", "result": {"score": 90}})

    client = make_backend_client(handler)
    try:
        response = client.poll_heat_intelligence("hi-act-2")
    finally:
        client.close()

    assert response["status"] == "Completed"
    assert response["result"] == {"score": 90}


# ── Report download frontend tests ──

DUMMY_PDF = b"%PDF-1.4 test frontend report bytes"


def test_frontend_client_downloads_report_success() -> None:
    """download_heat_intelligence_report returns raw PDF bytes."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/heat-intelligence/report/act-dl-001"
        return httpx.Response(
            200,
            content=DUMMY_PDF,
            headers={"content-type": "application/pdf"},
        )

    client = make_backend_client(handler)
    try:
        pdf_bytes = client.download_heat_intelligence_report("act-dl-001")
    finally:
        client.close()

    assert pdf_bytes == DUMMY_PDF


def test_frontend_client_download_report_410_expired() -> None:
    """download_heat_intelligence_report raises BackendAPIError on 410."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(410, json={"detail": "Link expired"})

    client = make_backend_client(handler)
    try:
        with pytest.raises(BackendAPIError) as exc_info:
            client.download_heat_intelligence_report("act-exp-001")
    finally:
        client.close()

    assert exc_info.value.status_code == 410
    assert "expired" in str(exc_info.value).lower()


def test_frontend_client_download_report_404() -> None:
    """download_heat_intelligence_report raises BackendAPIError on 404."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Report not found"})

    client = make_backend_client(handler)
    try:
        with pytest.raises(BackendAPIError) as exc_info:
            client.download_heat_intelligence_report("act-nf-001")
    finally:
        client.close()

    assert exc_info.value.status_code == 404


def test_frontend_client_download_report_empty() -> None:
    """download_heat_intelligence_report raises BackendAPIError for empty content."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    client = make_backend_client(handler)
    try:
        with pytest.raises(BackendAPIError, match="empty"):
            client.download_heat_intelligence_report("act-empty-001")
    finally:
        client.close()
