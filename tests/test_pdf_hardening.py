"""Hardening and defensive tests for Heat Intelligence PDF downloading and validation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import httpx
import pytest

from backend.api.exceptions import (
    InvalidRequestError,
    MalformedResponseError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TransportError,
)
from tests.conftest import make_client, status_payload


VALID_PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"
GARBAGE_HTML_BYTES = b"<html><body>Error 404 Not Found</body></html>"


def test_fetch_report_pdf_valid_magic_bytes() -> None:
    client = make_client(lambda _: httpx.Response(200))
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = VALID_PDF_BYTES
    mock_resp.headers = {"content-type": "application/pdf"}

    with patch("backend.api.client.httpx.Client") as MockHttpx:
        mock_fetcher = MagicMock()
        mock_fetcher.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_fetcher.__exit__ = MagicMock(return_value=False)
        mock_fetcher.get.return_value = mock_resp
        MockHttpx.return_value = mock_fetcher

        content = client.fetch_report_pdf("https://example.invalid/valid.pdf")

    assert content == VALID_PDF_BYTES
    client.close()


def test_fetch_report_pdf_rejects_invalid_magic_bytes() -> None:
    client = make_client(lambda _: httpx.Response(200))
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = GARBAGE_HTML_BYTES
    mock_resp.headers = {"content-type": "text/html"}

    with patch("backend.api.client.httpx.Client") as MockHttpx:
        mock_fetcher = MagicMock()
        mock_fetcher.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_fetcher.__exit__ = MagicMock(return_value=False)
        mock_fetcher.get.return_value = mock_resp
        MockHttpx.return_value = mock_fetcher

        with pytest.raises(MalformedResponseError, match="not a valid PDF"):
            client.fetch_report_pdf("https://example.invalid/fake.pdf")

    client.close()


def test_fetch_report_pdf_rejects_empty_bytes() -> None:
    client = make_client(lambda _: httpx.Response(200))
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b""
    mock_resp.headers = {}

    with patch("backend.api.client.httpx.Client") as MockHttpx:
        mock_fetcher = MagicMock()
        mock_fetcher.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_fetcher.__exit__ = MagicMock(return_value=False)
        mock_fetcher.get.return_value = mock_resp
        MockHttpx.return_value = mock_fetcher

        with pytest.raises(MalformedResponseError, match="empty"):
            client.fetch_report_pdf("https://example.invalid/empty.pdf")

    client.close()


def test_fetch_report_pdf_expired_url_410() -> None:
    client = make_client(lambda _: httpx.Response(200))
    mock_resp = MagicMock()
    mock_resp.status_code = 410
    mock_resp.content = b""
    mock_resp.headers = {}

    with patch("backend.api.client.httpx.Client") as MockHttpx:
        mock_fetcher = MagicMock()
        mock_fetcher.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_fetcher.__exit__ = MagicMock(return_value=False)
        mock_fetcher.get.return_value = mock_resp
        MockHttpx.return_value = mock_fetcher

        with pytest.raises(InvalidRequestError) as exc_info:
            client.fetch_report_pdf("https://example.invalid/expired.pdf")

    assert exc_info.value.http_status == 410
    assert "expired" in str(exc_info.value).lower()
    client.close()


def test_fetch_report_pdf_rate_limit_429() -> None:
    client = make_client(lambda _: httpx.Response(200))
    mock_resp = MagicMock()
    mock_resp.status_code = 429

    with patch("backend.api.client.httpx.Client") as MockHttpx:
        mock_fetcher = MagicMock()
        mock_fetcher.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_fetcher.__exit__ = MagicMock(return_value=False)
        mock_fetcher.get.return_value = mock_resp
        MockHttpx.return_value = mock_fetcher

        with pytest.raises(RateLimitError):
            client.fetch_report_pdf("https://example.invalid/ratelimit.pdf")

    client.close()


def test_fetch_report_pdf_server_error_500() -> None:
    client = make_client(lambda _: httpx.Response(200))
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch("backend.api.client.httpx.Client") as MockHttpx:
        mock_fetcher = MagicMock()
        mock_fetcher.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_fetcher.__exit__ = MagicMock(return_value=False)
        mock_fetcher.get.return_value = mock_resp
        MockHttpx.return_value = mock_fetcher

        with pytest.raises(ServerError):
            client.fetch_report_pdf("https://example.invalid/servererr.pdf")

    client.close()
