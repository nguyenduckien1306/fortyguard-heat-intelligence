"""Tests for the HeatIntelligenceService business logic layer."""

from __future__ import annotations

import httpx
import pytest

from backend.api.exceptions import AuthenticationError
from backend.config import Settings
from backend.services.heat_intelligence_service import HeatIntelligenceService
from tests.conftest import (
    make_client,
    sample_heat_intelligence_request,
    status_payload,
    submission_payload,
)


def test_service_submit_delegates_to_client() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=submission_payload("svc-hi-001"))

    client = make_client(handler)
    service = HeatIntelligenceService(client=client)
    response = service.submit_heat_intelligence(sample_heat_intelligence_request())

    assert response.activity_id == "svc-hi-001"


def test_service_get_status_delegates_to_client() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=status_payload("svc-hi-002", status="Processing"))

    client = make_client(handler)
    service = HeatIntelligenceService(client=client)
    status = service.get_heat_intelligence_status("svc-hi-002")

    assert status.activity_id == "svc-hi-002"
    assert status.status == "Processing"


def test_service_poll_delegates_to_client() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=status_payload("svc-hi-003", status="Completed"))

    client = make_client(handler)
    service = HeatIntelligenceService(client=client)
    status = service.poll_heat_intelligence("svc-hi-003", max_attempts=3, poll_interval_seconds=0.01)

    assert status.activity_id == "svc-hi-003"
    assert status.status == "Completed"


def test_service_raises_when_api_key_not_configured() -> None:
    unconfigured_settings = Settings(FORTYGUARD_API_KEY="")
    service = HeatIntelligenceService(settings=unconfigured_settings)

    with pytest.raises(AuthenticationError, match="not configured"):
        service.submit_heat_intelligence(sample_heat_intelligence_request())

    with pytest.raises(AuthenticationError, match="not configured"):
        service.get_heat_intelligence_status("act-1")

    with pytest.raises(AuthenticationError, match="not configured"):
        service.poll_heat_intelligence("act-1")
