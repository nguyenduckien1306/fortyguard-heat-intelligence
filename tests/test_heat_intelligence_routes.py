"""Tests for FastAPI Heat Intelligence routes."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from backend.api.exceptions import (
    AuthenticationError,
    InvalidRequestError,
    MalformedResponseError,
    NotFoundError,
    ServerError,
)
from backend.models.common import ActivityStatusResponse
from backend.models.heat_intelligence import HeatIntelligenceSubmissionResponse
from backend.routes.heat_intelligence import get_heat_intelligence_service
from backend.services.heat_intelligence_service import HeatIntelligenceService
from main import app
from tests.conftest import sample_heat_intelligence_request

# Dummy PDF bytes for test fixture — small valid-ish header
DUMMY_PDF_BYTES = b"%PDF-1.4 test report content for FortyGuard"


class DummyHeatIntelligenceService(HeatIntelligenceService):
    """Stub service for route-level isolation tests."""

    def __init__(self, mode: str = "success") -> None:
        self.mode = mode

    def submit_heat_intelligence(self, request) -> HeatIntelligenceSubmissionResponse:
        if self.mode == "auth_error":
            raise AuthenticationError("API key missing", http_status=401)
        if self.mode == "not_found_error":
            raise NotFoundError("Endpoint not found", http_status=404)
        if self.mode == "server_error":
            raise ServerError("Backend unavailable", http_status=500)
        return HeatIntelligenceSubmissionResponse(activity_id="route-hi-101")

    def get_heat_intelligence_status(self, activity_id: str) -> ActivityStatusResponse:
        if self.mode == "server_error":
            raise ServerError("Status check failed", http_status=500)
        return ActivityStatusResponse(
            activity_id=activity_id,
            status="Processing",
            result=None,
        )

    def poll_heat_intelligence(
        self,
        activity_id: str,
        *,
        max_attempts: int = 30,
        poll_interval_seconds: float = 2.0,
    ) -> ActivityStatusResponse:
        if self.mode == "server_error":
            raise ServerError("Polling failed", http_status=500)
        return ActivityStatusResponse(
            activity_id=activity_id,
            status="Completed",
            result={"analysis": "ok"},
        )

    def fetch_report(self, activity_id: str) -> bytes:
        if self.mode == "report_processing":
            raise InvalidRequestError(
                "Task is still processing. Report is not ready yet.",
                http_status=409,
            )
        if self.mode == "report_expired":
            raise InvalidRequestError(
                "The report download link has expired or is unauthorized.",
                http_status=410,
            )
        if self.mode == "report_not_found":
            raise NotFoundError(
                "The requested report file was not found.",
                http_status=404,
            )
        if self.mode == "server_error":
            raise ServerError("Storage provider error", http_status=502)
        if self.mode == "report_malformed":
            raise MalformedResponseError(
                "Completed task has no result payload.",
            )
        return DUMMY_PDF_BYTES


def test_post_heat_intelligence_success() -> None:
    app.dependency_overrides[get_heat_intelligence_service] = (
        lambda: DummyHeatIntelligenceService("success")
    )
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/heat-intelligence/",
            json=sample_heat_intelligence_request().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "activity_id": "route-hi-101",
        "message": "Heat intelligence task submitted successfully",
    }


def test_post_heat_intelligence_translates_provider_error() -> None:
    app.dependency_overrides[get_heat_intelligence_service] = (
        lambda: DummyHeatIntelligenceService("auth_error")
    )
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/heat-intelligence/",
            json=sample_heat_intelligence_request().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert "API key missing" in response.json()["detail"]


def test_post_heat_intelligence_translates_404_error() -> None:
    app.dependency_overrides[get_heat_intelligence_service] = (
        lambda: DummyHeatIntelligenceService("not_found_error")
    )
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/heat-intelligence/",
            json=sample_heat_intelligence_request().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "Endpoint not found" in response.json()["detail"]



def test_get_heat_intelligence_status_route() -> None:
    app.dependency_overrides[get_heat_intelligence_service] = (
        lambda: DummyHeatIntelligenceService("success")
    )
    client = TestClient(app)
    try:
        response = client.get("/api/v1/heat-intelligence/status/act-999")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "activity_id": "act-999",
        "status": "Processing",
        "result": None,
        "diagnostic": None,
    }


def test_poll_heat_intelligence_status_route() -> None:
    app.dependency_overrides[get_heat_intelligence_service] = (
        lambda: DummyHeatIntelligenceService("success")
    )
    client = TestClient(app)
    try:
        response = client.get(
            "/api/v1/heat-intelligence/status/act-999/poll",
            params={"max_attempts": 5, "poll_interval_seconds": 0.1},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "Completed"
    assert response.json()["result"] == {"analysis": "ok"}


# ── Report download route tests ──


def test_report_download_success() -> None:
    """GET /report/{id} returns PDF bytes with correct headers."""
    app.dependency_overrides[get_heat_intelligence_service] = (
        lambda: DummyHeatIntelligenceService("success")
    )
    client = TestClient(app)
    try:
        response = client.get("/api/v1/heat-intelligence/report/act-pdf-001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == DUMMY_PDF_BYTES
    assert response.headers["content-type"] == "application/pdf"
    assert "heat_intelligence_report_act-pdf-001.pdf" in response.headers["content-disposition"]


def test_report_download_still_processing() -> None:
    """GET /report/{id} returns 409 when task is still processing."""
    app.dependency_overrides[get_heat_intelligence_service] = (
        lambda: DummyHeatIntelligenceService("report_processing")
    )
    client = TestClient(app)
    try:
        response = client.get("/api/v1/heat-intelligence/report/act-proc-001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "still processing" in response.json()["detail"].lower()


def test_report_download_expired_link() -> None:
    """GET /report/{id} returns 410 when the signed download link has expired."""
    app.dependency_overrides[get_heat_intelligence_service] = (
        lambda: DummyHeatIntelligenceService("report_expired")
    )
    client = TestClient(app)
    try:
        response = client.get("/api/v1/heat-intelligence/report/act-exp-001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 410
    assert "expired" in response.json()["detail"].lower()


def test_report_download_not_found() -> None:
    """GET /report/{id} returns 404 when PDF is not on storage."""
    app.dependency_overrides[get_heat_intelligence_service] = (
        lambda: DummyHeatIntelligenceService("report_not_found")
    )
    client = TestClient(app)
    try:
        response = client.get("/api/v1/heat-intelligence/report/act-nf-001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_report_download_server_error() -> None:
    """GET /report/{id} returns 502 when storage provider fails."""
    app.dependency_overrides[get_heat_intelligence_service] = (
        lambda: DummyHeatIntelligenceService("server_error")
    )
    client = TestClient(app)
    try:
        response = client.get("/api/v1/heat-intelligence/report/act-err-001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert "error" in response.json()["detail"].lower()


def test_report_download_malformed_result() -> None:
    """GET /report/{id} returns 502 when result has no download_link."""
    app.dependency_overrides[get_heat_intelligence_service] = (
        lambda: DummyHeatIntelligenceService("report_malformed")
    )
    client = TestClient(app)
    try:
        response = client.get("/api/v1/heat-intelligence/report/act-mal-001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert "no result" in response.json()["detail"].lower()
