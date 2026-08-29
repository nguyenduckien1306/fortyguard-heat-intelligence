"""Phase 16 — Step 16.8: Provider Contract Verification Test Suite.

Validates that the FortyGuardClient correctly parses every contract shape
from the FortyGuard provider, including:

1.  Submission contract: successful POST → activity_id extraction
2.  Status contract: Processing, Completed, Failed lifecycle
3.  Completed result parsing: result dict, download_link, metric payloads
4.  Failed status diagnostic extraction: code, message, reason, details
5.  Error envelope parsing: error=True + status_code + message
6.  Edge-case status values: unknown, empty, null
7.  Activity ID mismatch detection
8.  Boolean/non-integer status_code in error envelope
9.  PDF report contract: fetch_report_pdf, get_heat_intelligence_report_pdf
10. Sanitization of diagnostic payloads containing credentials
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from backend.api.client import FortyGuardClient
from backend.api.exceptions import (
    FortyGuardClientError,
    InvalidRequestError,
    MalformedResponseError,
    NotFoundError,
    ServerError,
    TransportError,
)
from backend.models.common import ActivityStatusResponse
from tests.conftest import (
    make_client,
    sample_heat_intelligence_request,
    sample_heatmap_request,
    status_payload,
    submission_payload,
)


# ══════════════════════════════════════════════════════════════════════════════
# Section 1: Submission Contract Verification
# ══════════════════════════════════════════════════════════════════════════════


class TestSubmissionContract:
    """Verify the POST /v1/heatmap and POST /v1/heat_intelligence response contracts."""

    def test_heatmap_submission_returns_activity_id(self) -> None:
        """Successful heatmap submission extracts activity_id from data envelope."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=submission_payload("hm-act-001"))

        client = make_client(handler)
        try:
            result = client.create_heatmap_request(sample_heatmap_request())
            assert result.activity_id == "hm-act-001"
        finally:
            client.close()

    def test_heat_intelligence_submission_returns_activity_id(self) -> None:
        """Successful heat intelligence submission extracts activity_id."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=submission_payload("hi-act-001"))

        client = make_client(handler)
        try:
            result = client.create_heat_intelligence_request(sample_heat_intelligence_request())
            assert result.activity_id == "hi-act-001"
        finally:
            client.close()

    def test_submission_sends_correct_http_method(self) -> None:
        """Submission uses POST method."""
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            return httpx.Response(200, json=submission_payload("act-method"))

        client = make_client(handler)
        try:
            client.create_heatmap_request(sample_heatmap_request())
            assert captured["method"] == "POST"
        finally:
            client.close()

    def test_submission_sends_api_key_header(self) -> None:
        """Submission includes the api-key header."""
        captured_headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json=submission_payload("act-auth"))

        client = make_client(handler, api_key="my-test-key")
        try:
            client.create_heatmap_request(sample_heatmap_request())
            assert captured_headers.get("api-key") == "my-test-key"
        finally:
            client.close()

    def test_submission_sends_json_content_type(self) -> None:
        """Submission sends Content-Type: application/json."""
        captured_headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json=submission_payload("act-ct"))

        client = make_client(handler)
        try:
            client.create_heatmap_request(sample_heatmap_request())
            assert "application/json" in captured_headers.get("content-type", "")
        finally:
            client.close()


# ══════════════════════════════════════════════════════════════════════════════
# Section 2: Status Contract Verification
# ══════════════════════════════════════════════════════════════════════════════


class TestStatusContract:
    """Verify GET /v1/status/{activity_id} contract parsing."""

    def test_processing_status_parsed(self) -> None:
        """Processing status is correctly parsed."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=status_payload("act-proc", status="Processing"))

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-proc")
            assert result.activity_id == "act-proc"
            assert result.status == "Processing"
            assert result.result is None
        finally:
            client.close()

    def test_completed_status_with_result(self) -> None:
        """Completed status with result dict is correctly parsed."""
        result_data = {"download_link": "https://example.com/report.pdf", "format": "pdf"}

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=status_payload("act-done", status="Completed", result=result_data))

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-done")
            assert result.status == "Completed"
            assert result.result is not None
            assert result.result["format"] == "pdf"
        finally:
            client.close()

    def test_failed_status_parsed_with_diagnostic(self) -> None:
        """Failed status produces diagnostic dict with extracted fields."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {
                    "activity_id": "act-fail",
                    "status": "Failed",
                    "code": "PROVIDER_ERROR",
                    "message": "Satellite data unavailable",
                    "reason": "Data gap in AOI",
                },
            })

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-fail")
            assert result.status == "Failed"
            assert result.diagnostic is not None
            assert result.diagnostic.get("code") == "PROVIDER_ERROR"
            assert "unavailable" in result.diagnostic.get("message", "")
            assert "gap" in result.diagnostic.get("reason", "")
        finally:
            client.close()

    def test_failed_status_with_nested_details(self) -> None:
        """Failed status with nested details field is preserved in diagnostic."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {
                    "activity_id": "act-detail",
                    "status": "Failed",
                    "details": {"error_code": "AOI_TOO_LARGE", "max_area_km2": 100},
                },
            })

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-detail")
            assert result.status == "Failed"
            assert result.diagnostic is not None
            assert "details" in result.diagnostic
        finally:
            client.close()

    def test_activity_id_mismatch_raises_malformed(self) -> None:
        """Status response with mismatched activity_id raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=status_payload("wrong-id", status="Completed"))

        client = make_client(handler)
        try:
            with pytest.raises(MalformedResponseError, match="different activity_id"):
                client.get_activity_status("expected-id")
        finally:
            client.close()

    def test_completed_without_result_key_extracts_extra_fields(self) -> None:
        """Completed status without explicit 'result' extracts remaining fields as result."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {
                    "activity_id": "act-nokey",
                    "status": "Completed",
                    "download_link": "https://cdn.fortyguard.com/report.pdf",
                    "format": "pdf",
                },
            })

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-nokey")
            assert result.status == "Completed"
            assert result.result is not None
            assert "download_link" in result.result
        finally:
            client.close()


# ══════════════════════════════════════════════════════════════════════════════
# Section 3: Error Envelope Contract
# ══════════════════════════════════════════════════════════════════════════════


class TestErrorEnvelopeContract:
    """Verify error=True envelope parsing."""

    def test_error_envelope_with_status_code(self) -> None:
        """error=True with status_code=401 raises AuthenticationError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": True,
                "status_code": 401,
                "message": "Invalid API key",
                "data": None,
            })

        client = make_client(handler)
        try:
            with pytest.raises(FortyGuardClientError):
                client.create_heatmap_request(sample_heatmap_request())
        finally:
            client.close()

    def test_error_envelope_preserves_message(self) -> None:
        """Error envelope message is preserved in exception."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": True,
                "status_code": 422,
                "message": "Invalid polygon coordinates",
            })

        client = make_client(handler)
        try:
            with pytest.raises(InvalidRequestError, match="Invalid polygon"):
                client.create_heatmap_request(sample_heatmap_request())
        finally:
            client.close()

    def test_error_envelope_boolean_status_code_raises_malformed(self) -> None:
        """Boolean status_code in error envelope raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": True,
                "status_code": True,
                "message": "Something broke",
            })

        client = make_client(handler)
        try:
            with pytest.raises(MalformedResponseError, match="invalid status_code"):
                client.create_heatmap_request(sample_heatmap_request())
        finally:
            client.close()


# ══════════════════════════════════════════════════════════════════════════════
# Section 4: Edge-Case Status Values
# ══════════════════════════════════════════════════════════════════════════════


class TestEdgeCaseStatuses:
    """Verify handling of unusual or unexpected status values."""

    def test_unknown_status_string_returned_as_is(self) -> None:
        """Unknown status like 'Queued' is returned as-is."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=status_payload("act-queued", status="Queued"))

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-queued")
            assert result.status == "Queued"
        finally:
            client.close()

    def test_status_empty_string_raises_malformed(self) -> None:
        """Empty string status raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {"activity_id": "act-empty", "status": ""},
            })

        client = make_client(handler)
        try:
            with pytest.raises(MalformedResponseError, match="status"):
                client.get_activity_status("act-empty")
        finally:
            client.close()

    def test_status_null_raises_malformed(self) -> None:
        """Null status raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {"activity_id": "act-null", "status": None},
            })

        client = make_client(handler)
        try:
            with pytest.raises(MalformedResponseError, match="status"):
                client.get_activity_status("act-null")
        finally:
            client.close()

    def test_status_numeric_raises_malformed(self) -> None:
        """Numeric status (int instead of string) raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {"activity_id": "act-num", "status": 200},
            })

        client = make_client(handler)
        try:
            with pytest.raises(MalformedResponseError, match="status"):
                client.get_activity_status("act-num")
        finally:
            client.close()


# ══════════════════════════════════════════════════════════════════════════════
# Section 5: PDF Report Contract
# ══════════════════════════════════════════════════════════════════════════════


class TestPDFReportContract:
    """Verify the PDF download / report retrieval contract."""

    def test_fetch_report_pdf_valid(self) -> None:
        """Valid PDF response returns bytes with PDF magic prefix."""
        pdf_bytes = b"%PDF-1.4 fake pdf content"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=pdf_bytes, headers={"content-type": "application/pdf"})

        settings = _make_settings()
        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(base_url="https://api.fortyguard.com", transport=transport)
        client = FortyGuardClient(settings=settings, http_client=http_client)
        try:
            result = client.fetch_report_pdf("https://cdn.example.com/report.pdf?Signature=abc")
            assert result == pdf_bytes
        finally:
            client.close()

    def test_fetch_report_pdf_empty_link_raises(self) -> None:
        """Empty download link raises InvalidRequestError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200)

        client = make_client(handler)
        try:
            with pytest.raises(InvalidRequestError, match="Invalid"):
                client.fetch_report_pdf("")
        finally:
            client.close()

    def test_fetch_report_pdf_expired_link(self) -> None:
        """Expired/unauthorized link (403/410) raises InvalidRequestError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="Forbidden")

        settings = _make_settings()
        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(base_url="https://api.fortyguard.com", transport=transport)
        client = FortyGuardClient(settings=settings, http_client=http_client)
        try:
            with pytest.raises(InvalidRequestError, match="expired"):
                client.fetch_report_pdf("https://cdn.example.com/report.pdf")
        finally:
            client.close()

    def test_fetch_report_pdf_empty_content(self) -> None:
        """200 with empty body raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"")

        settings = _make_settings()
        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(base_url="https://api.fortyguard.com", transport=transport)
        client = FortyGuardClient(settings=settings, http_client=http_client)
        try:
            with pytest.raises(MalformedResponseError, match="empty"):
                client.fetch_report_pdf("https://cdn.example.com/report.pdf")
        finally:
            client.close()

    def test_fetch_report_non_pdf_content_raises(self) -> None:
        """Non-PDF content (no PDF magic, wrong content-type) raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>Not a PDF</html>", headers={"content-type": "text/html"})

        settings = _make_settings()
        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(base_url="https://api.fortyguard.com", transport=transport)
        client = FortyGuardClient(settings=settings, http_client=http_client)
        try:
            with pytest.raises(MalformedResponseError, match="PDF"):
                client.fetch_report_pdf("https://cdn.example.com/report.pdf")
        finally:
            client.close()

    def test_get_heat_intelligence_report_processing_raises(self) -> None:
        """Retrieving report while still Processing raises InvalidRequestError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=status_payload("act-proc", status="Processing"))

        client = make_client(handler)
        try:
            with pytest.raises(InvalidRequestError, match="still processing"):
                client.get_heat_intelligence_report_pdf("act-proc")
        finally:
            client.close()

    def test_get_heat_intelligence_report_failed_raises(self) -> None:
        """Retrieving report for Failed task raises InvalidRequestError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=status_payload("act-f", status="Failed"))

        client = make_client(handler)
        try:
            with pytest.raises(InvalidRequestError, match="failed"):
                client.get_heat_intelligence_report_pdf("act-f")
        finally:
            client.close()

    def test_fetch_report_pdf_does_not_forward_api_key(self) -> None:
        """Storage downloads must not attach the FortyGuard api-key header."""
        captured_headers: dict[str, str] = {}
        pdf_bytes = b"%PDF-1.4 safe"

        def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, content=pdf_bytes, headers={"content-type": "application/pdf"})

        settings = _make_settings()
        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(
            base_url="https://api.fortyguard.com",
            transport=transport,
            headers={"api-key": "must-not-leak", "Content-Type": "application/json"},
        )
        client = FortyGuardClient(settings=settings, http_client=http_client)
        try:
            result = client.fetch_report_pdf("https://cdn.example.com/report.pdf?Signature=abc")
            assert result == pdf_bytes
            assert captured_headers.get("api-key") is None
        finally:
            client.close()


# ══════════════════════════════════════════════════════════════════════════════
# Section 6: Diagnostic Credential Sanitization in Provider Contract
# ══════════════════════════════════════════════════════════════════════════════


class TestContractSanitization:
    """Verify credential fields are never leaked in parsed diagnostics."""

    def test_download_link_stripped_from_diagnostics(self) -> None:
        """download_link is stripped from Failed diagnostics."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {
                    "activity_id": "act-dl",
                    "status": "Failed",
                    "download_link": "https://s3.amazonaws.com/bucket/key?X-Amz-Signature=secret",
                    "message": "Processing failed",
                },
            })

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-dl")
            diag_str = json.dumps(result.diagnostic) if result.diagnostic else ""
            assert "s3.amazonaws.com" not in diag_str
            assert "X-Amz-Signature" not in diag_str
        finally:
            client.close()

    def test_auth_header_stripped_from_diagnostics(self) -> None:
        """Authorization/headers fields are stripped from diagnostics."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {
                    "activity_id": "act-hdr",
                    "status": "Failed",
                    "headers": {"Authorization": "Bearer token123"},
                    "message": "Auth fail",
                },
            })

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-hdr")
            diag_str = json.dumps(result.diagnostic) if result.diagnostic else ""
            assert "Bearer" not in diag_str
            assert "token123" not in diag_str
        finally:
            client.close()

    def test_cookie_fields_stripped(self) -> None:
        """Cookie fields are stripped from diagnostics."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {
                    "activity_id": "act-cookie",
                    "status": "Failed",
                    "cookie": "session=abc123; csrf=xyz",
                },
            })

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-cookie")
            diag_str = json.dumps(result.diagnostic) if result.diagnostic else ""
            assert "abc123" not in diag_str
        finally:
            client.close()


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════


def _make_settings() -> Any:
    from backend.config import Settings
    return Settings(
        FORTYGUARD_API_KEY="test-key",
        FORTYGUARD_BASE_URL="https://api.fortyguard.com",
    )
