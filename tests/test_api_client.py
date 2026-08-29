"""Tests for FortyGuard API client initialization."""

from unittest.mock import patch

import httpx
import pytest

from backend.api.client import FortyGuardClient
from backend.config import Settings


def test_client_initialization_uses_api_key_header() -> None:
    settings = Settings(
        FORTYGUARD_API_KEY="test-key",
        FORTYGUARD_BASE_URL="https://api.fortyguard.com",
    )
    client = FortyGuardClient(settings=settings)

    assert client.base_url == "https://api.fortyguard.com"
    assert client._http_client.headers["api-key"] == "test-key"
    assert "Authorization" not in client._http_client.headers

    client.close()


def test_client_does_not_send_api_key_when_unconfigured() -> None:
    settings = Settings(
        FORTYGUARD_API_KEY="",
        FORTYGUARD_BASE_URL="https://api.fortyguard.com",
    )
    client = FortyGuardClient(settings=settings)

    assert "api-key" not in client._http_client.headers
    client.close()


def test_get_credits_usage_not_implemented_in_phase_1() -> None:
    settings = Settings(FORTYGUARD_API_KEY="test-key")
    client = FortyGuardClient(settings=settings)

    with pytest.raises(NotImplementedError):
        client.get_credits_usage()

    client.close()


def test_client_context_manager_closes_http_client() -> None:
    settings = Settings(FORTYGUARD_API_KEY="test-key")
    with patch.object(httpx.Client, "close") as mock_close:
        with FortyGuardClient(settings=settings):
            pass
        mock_close.assert_called_once()
