"""Tests for the heatmap service layer."""

from unittest.mock import Mock

import httpx
import pytest

from backend.api.exceptions import AuthenticationError, NotFoundError
from backend.api.client import FortyGuardClient
from backend.config import Settings
from backend.models.common import ActivityStatusResponse
from backend.services.heatmap_service import HeatmapService
from tests.conftest import make_client, sample_heatmap_request, submission_payload


def test_service_requires_api_key_configuration() -> None:
    settings = Settings(FORTYGUARD_API_KEY="", FORTYGUARD_BASE_URL="https://api.fortyguard.com")
    client = make_client(lambda _: httpx.Response(200, json=submission_payload()), api_key="")
    service = HeatmapService(client=client, settings=settings)

    with pytest.raises(AuthenticationError, match="not configured"):
        service.submit_heatmap(sample_heatmap_request())

    client.close()


def test_service_submit_heatmap_delegates_to_client() -> None:
    settings = Settings(
        FORTYGUARD_API_KEY="test-key",
        FORTYGUARD_BASE_URL="https://api.fortyguard.com",
    )
    client = make_client(lambda _: httpx.Response(200, json=submission_payload("svc-99")))
    service = HeatmapService(client=client, settings=settings)

    result = service.submit_heatmap(sample_heatmap_request())

    assert result.activity_id == "svc-99"
    client.close()


def test_service_propagates_client_failure() -> None:
    settings = Settings(FORTYGUARD_API_KEY="test-key")
    client = Mock(spec=FortyGuardClient)
    client.create_heatmap_request.side_effect = NotFoundError("Activity unavailable")
    service = HeatmapService(client=client, settings=settings)

    with pytest.raises(NotFoundError, match="Activity unavailable"):
        service.submit_heatmap(sample_heatmap_request())


def test_service_retrieves_processing_status() -> None:
    settings = Settings(FORTYGUARD_API_KEY="test-key")
    client = Mock(spec=FortyGuardClient)
    client.get_activity_status.return_value = ActivityStatusResponse(
        activity_id="svc-activity",
        status="Processing",
    )
    service = HeatmapService(client=client, settings=settings)

    result = service.get_heatmap_status("svc-activity")

    assert result.status == "Processing"
    client.get_activity_status.assert_called_once_with("svc-activity")


def test_service_returns_failed_status_without_inventing_reason() -> None:
    settings = Settings(FORTYGUARD_API_KEY="test-key")
    client = Mock(spec=FortyGuardClient)
    client.get_activity_status.return_value = ActivityStatusResponse(
        activity_id="svc-failed",
        status="Failed",
    )
    service = HeatmapService(client=client, settings=settings)

    result = service.get_heatmap_status("svc-failed")

    assert result.status == "Failed"
    assert result.result is None
