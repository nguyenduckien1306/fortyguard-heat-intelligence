"""Tests for FortyGuard Heat Intelligence client HTTP behavior (mocked)."""

from __future__ import annotations

import httpx
import pytest

from backend.api.exceptions import (
    AuthenticationError,
    ForbiddenError,
    InvalidRequestError,
    MalformedResponseError,
    NotFoundError,
    PollingTimeoutError,
    RateLimitError,
    ServerError,
)
from tests.conftest import (
    make_client,
    sample_heat_intelligence_request,
    status_payload,
    submission_payload,
)


def test_successful_heat_intelligence_submission() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        assert request.headers["api-key"] == "test-key"
        assert "Authorization" not in request.headers
        return httpx.Response(200, json=submission_payload("heat-intel-001"))

    client = make_client(handler)
    try:
        response = client.create_heat_intelligence_request(sample_heat_intelligence_request())
    finally:
        client.close()

    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/heat_intelligence"
    assert response.activity_id == "heat-intel-001"



def test_heat_intelligence_missing_activity_id() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": False, "data": {}})

    client = make_client(handler)
    try:
        with pytest.raises(MalformedResponseError):
            client.create_heat_intelligence_request(sample_heat_intelligence_request())
    finally:
        client.close()


@pytest.mark.parametrize(
    ("status_code", "expected_exception"),
    [
        (400, InvalidRequestError),
        (401, AuthenticationError),
        (403, ForbiddenError),
        (404, NotFoundError),
        (429, RateLimitError),
        (500, ServerError),
    ],
)
def test_heat_intelligence_http_errors(
    status_code: int,
    expected_exception: type[Exception],
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": True, "message": "API error"})

    client = make_client(handler)
    try:
        with pytest.raises(expected_exception):
            client.create_heat_intelligence_request(sample_heat_intelligence_request())
    finally:
        client.close()


def test_poll_heat_intelligence_success() -> None:
    responses = [
        status_payload("hi-act-1", status="Processing"),
        status_payload("hi-act-1", status="Completed", result={"insights": "test"}),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    client = make_client(handler)
    try:
        status = client.poll_heat_intelligence_result("hi-act-1", max_attempts=5, poll_interval_seconds=0.01)
    finally:
        client.close()

    assert status.status == "Completed"
    assert status.result == {"insights": "test"}


def test_poll_heat_intelligence_failed() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=status_payload("hi-act-2", status="Failed"))

    client = make_client(handler)
    try:
        status = client.poll_heat_intelligence_result("hi-act-2", max_attempts=5, poll_interval_seconds=0.01)
    finally:
        client.close()

    assert status.status == "Failed"


def test_poll_heat_intelligence_timeout() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=status_payload("hi-act-3", status="Processing"))

    client = make_client(handler)
    try:
        with pytest.raises(PollingTimeoutError):
            client.poll_heat_intelligence_result("hi-act-3", max_attempts=2, poll_interval_seconds=0.01)
    finally:
        client.close()


# ── Report PDF download tests ──

from unittest.mock import patch, MagicMock
from backend.api.exceptions import TransportError


REPORT_PDF = b"%PDF-1.4 test heat intelligence report content"


def test_fetch_report_pdf_success() -> None:
    """fetch_report_pdf returns PDF bytes from a signed URL."""
    client = make_client(lambda _: httpx.Response(200))

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = REPORT_PDF

    with patch("backend.api.client.httpx.Client") as MockHttpxClient:
        mock_fetcher = MagicMock()
        mock_fetcher.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_fetcher.__exit__ = MagicMock(return_value=False)
        mock_fetcher.get.return_value = mock_response
        MockHttpxClient.return_value = mock_fetcher

        result = client.fetch_report_pdf("https://example.invalid/report.pdf")

    assert result == REPORT_PDF
    client.close()


def test_fetch_report_pdf_expired_link() -> None:
    """fetch_report_pdf raises InvalidRequestError for 403/410 responses."""
    client = make_client(lambda _: httpx.Response(200))

    mock_response = MagicMock()
    mock_response.status_code = 410
    mock_response.content = b""

    with patch("backend.api.client.httpx.Client") as MockHttpxClient:
        mock_fetcher = MagicMock()
        mock_fetcher.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_fetcher.__exit__ = MagicMock(return_value=False)
        mock_fetcher.get.return_value = mock_response
        MockHttpxClient.return_value = mock_fetcher

        with pytest.raises(InvalidRequestError, match="expired"):
            client.fetch_report_pdf("https://example.invalid/expired.pdf")

    client.close()


def test_fetch_report_pdf_transport_error() -> None:
    """fetch_report_pdf raises TransportError when network fails."""
    client = make_client(lambda _: httpx.Response(200))

    with patch("backend.api.client.httpx.Client") as MockHttpxClient:
        mock_fetcher = MagicMock()
        mock_fetcher.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_fetcher.__exit__ = MagicMock(return_value=False)
        mock_fetcher.get.side_effect = httpx.ConnectError("Connection refused")
        MockHttpxClient.return_value = mock_fetcher

        with pytest.raises(TransportError, match="storage provider"):
            client.fetch_report_pdf("https://example.invalid/network-fail.pdf")

    client.close()


def test_fetch_report_pdf_invalid_link() -> None:
    """fetch_report_pdf raises InvalidRequestError for empty or None link."""
    client = make_client(lambda _: httpx.Response(200))

    with pytest.raises(InvalidRequestError, match="Invalid"):
        client.fetch_report_pdf("")

    with pytest.raises(InvalidRequestError, match="Invalid"):
        client.fetch_report_pdf("   ")

    client.close()


def test_get_heat_intelligence_report_pdf_still_processing() -> None:
    """get_heat_intelligence_report_pdf raises InvalidRequestError for processing task."""
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=status_payload("hi-rpt-1", status="Processing"))

    client = make_client(handler)
    try:
        with pytest.raises(InvalidRequestError, match="still processing"):
            client.get_heat_intelligence_report_pdf("hi-rpt-1")
    finally:
        client.close()


def test_get_heat_intelligence_report_pdf_no_download_link() -> None:
    """get_heat_intelligence_report_pdf raises MalformedResponseError when result has no link."""
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=status_payload("hi-rpt-2", status="Completed", result={"other": "data"}))

    client = make_client(handler)
    try:
        with pytest.raises(MalformedResponseError, match="download_link"):
            client.get_heat_intelligence_report_pdf("hi-rpt-2")
    finally:
        client.close()
