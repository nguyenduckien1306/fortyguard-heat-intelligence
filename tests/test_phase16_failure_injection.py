"""Phase 16 — Step 16.7: Failure Injection & Recovery Test Suite.

Validates system resilience to:
1. Provider HTTP errors (500, 429, 401, 403, 404, 502)
2. Malformed / non-JSON responses
3. NaN / Inf / None values in metrics
4. Partial / incomplete payloads
5. Unicode and special character injection
6. Network transport failures
7. Polling timeout recovery
8. Credential / secret sanitization in failure diagnostics
9. Intelligence pipeline resilience to garbage inputs
10. Recovery semantics after transient failures
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import datetime, timezone

import httpx
import pytest
import streamlit as st

from backend.api.client import FortyGuardClient
from backend.api.exceptions import (
    AuthenticationError,
    ForbiddenError,
    FortyGuardClientError,
    InvalidRequestError,
    MalformedResponseError,
    NotFoundError,
    PollingTimeoutError,
    RateLimitError,
    ServerError,
    TransportError,
)
from backend.config import Settings
from backend.models.common import ActivityStatusResponse
from tests.conftest import make_client, sample_heat_intelligence_request, status_payload, submission_payload

from frontend.utils.analysis_history import AnalysisRecord
from frontend.utils.clock import FrozenClock
from frontend.utils.evidence import build_evidence_bundle, calculate_evidence_hash
from frontend.utils.phase15_orchestrator import run_phase15_intelligence
from frontend.utils.signal_pipeline import generate_pipeline_signals
from frontend.utils.watchlists import Watchlist, WatchlistCriterion


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_record(idx: int, metrics: dict | None = None) -> AnalysisRecord:
    now = datetime.now(timezone.utc).isoformat()
    default_metrics = {"mean_temp": 41.0, "temp_spread": 10.0, "total_tiles": 80}
    return AnalysisRecord(
        analysis_id=f"FAIL-INJ-{idx:03d}",
        activity_id=f"act_fail_{idx:03d}",
        analysis_type="heatmap",
        created_at=now,
        updated_at=now,
        location_label="FailTest-Zone",
        date="2026-08-23",
        metrics=metrics or default_metrics,
        summary="Failure injection test record.",
    )


@pytest.fixture(autouse=True)
def _clean_session():
    """Ensure clean session state for each test."""
    if hasattr(st, "session_state"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
    yield
    if hasattr(st, "session_state"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]


# ══════════════════════════════════════════════════════════════════════════════
# Section 1: Provider HTTP Error Injection
# ══════════════════════════════════════════════════════════════════════════════


class TestProviderHTTPErrors:
    """Verify correct exception mapping for every provider HTTP error code."""

    @pytest.mark.parametrize(
        ("status_code", "expected_exc"),
        [
            (400, InvalidRequestError),
            (401, AuthenticationError),
            (403, ForbiddenError),
            (404, NotFoundError),
            (422, InvalidRequestError),
            (429, RateLimitError),
            (500, ServerError),
        ],
    )
    def test_submission_http_error_mapping(self, status_code: int, expected_exc: type) -> None:
        """Each HTTP error code maps to the correct typed exception."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, json={"error": True, "message": f"Error {status_code}"})

        client = make_client(handler)
        try:
            with pytest.raises(expected_exc) as exc_info:
                client.create_heat_intelligence_request(sample_heat_intelligence_request())
            assert exc_info.value.http_status == status_code
        finally:
            client.close()

    def test_server_500_preserves_message(self) -> None:
        """500 error preserves the provider error message."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": True, "message": "Internal processing failure"})

        client = make_client(handler)
        try:
            with pytest.raises(ServerError, match="Internal processing failure"):
                client.create_heat_intelligence_request(sample_heat_intelligence_request())
        finally:
            client.close()

    def test_429_rate_limit_with_retry_after(self) -> None:
        """429 errors are correctly classified even with retry-after headers."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                headers={"retry-after": "30"},
                json={"error": True, "message": "Too many requests"},
            )

        client = make_client(handler)
        try:
            with pytest.raises(RateLimitError):
                client.create_heat_intelligence_request(sample_heat_intelligence_request())
        finally:
            client.close()

    def test_unknown_status_code_falls_back_to_base(self) -> None:
        """Unmapped HTTP status codes raise the base FortyGuardClientError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(502, text="Bad Gateway")

        client = make_client(handler)
        try:
            with pytest.raises(FortyGuardClientError):
                client.create_heat_intelligence_request(sample_heat_intelligence_request())
        finally:
            client.close()


# ══════════════════════════════════════════════════════════════════════════════
# Section 2: Malformed Response Injection
# ══════════════════════════════════════════════════════════════════════════════


class TestMalformedResponses:
    """Verify graceful handling of non-JSON, empty, and garbled responses."""

    def test_non_json_response_raises_malformed(self) -> None:
        """Plain text / HTML response raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>Not JSON</html>", headers={"content-type": "text/html"})

        client = make_client(handler)
        try:
            with pytest.raises(MalformedResponseError):
                client.create_heat_intelligence_request(sample_heat_intelligence_request())
        finally:
            client.close()

    def test_empty_body_200_raises_malformed(self) -> None:
        """200 with empty body raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="")

        client = make_client(handler)
        try:
            with pytest.raises((MalformedResponseError, FortyGuardClientError)):
                client.create_heat_intelligence_request(sample_heat_intelligence_request())
        finally:
            client.close()

    def test_json_array_instead_of_object_raises_malformed(self) -> None:
        """JSON array instead of object raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[{"activity_id": "abc"}])

        client = make_client(handler)
        try:
            with pytest.raises(MalformedResponseError, match="JSON object"):
                client.create_heat_intelligence_request(sample_heat_intelligence_request())
        finally:
            client.close()

    def test_missing_data_key_raises_malformed(self) -> None:
        """Response without 'data' key raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": False, "message": "OK"})

        client = make_client(handler)
        try:
            with pytest.raises(MalformedResponseError, match="Missing data"):
                client.create_heat_intelligence_request(sample_heat_intelligence_request())
        finally:
            client.close()

    def test_null_activity_id_raises_malformed(self) -> None:
        """Null activity_id in submission response raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": False, "data": {"activity_id": None}})

        client = make_client(handler)
        try:
            with pytest.raises(MalformedResponseError, match="activity_id"):
                client.create_heat_intelligence_request(sample_heat_intelligence_request())
        finally:
            client.close()

    def test_empty_string_activity_id_raises_malformed(self) -> None:
        """Empty string activity_id raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": False, "data": {"activity_id": ""}})

        client = make_client(handler)
        try:
            with pytest.raises(MalformedResponseError, match="activity_id"):
                client.create_heat_intelligence_request(sample_heat_intelligence_request())
        finally:
            client.close()

    def test_status_missing_status_field_raises_malformed(self) -> None:
        """Status response without 'status' field raises MalformedResponseError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": False, "data": {"activity_id": "act-001"}})

        client = make_client(handler)
        try:
            with pytest.raises(MalformedResponseError, match="status"):
                client.get_activity_status("act-001")
        finally:
            client.close()


# ══════════════════════════════════════════════════════════════════════════════
# Section 3: Transport / Network Failure Injection
# ══════════════════════════════════════════════════════════════════════════════


class TestTransportFailures:
    """Verify graceful handling of network-level failures."""

    def test_connection_refused_raises_transport_error(self) -> None:
        """Connection failure raises TransportError."""
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = make_client(handler)
        try:
            with pytest.raises(TransportError, match="Unable to reach FortyGuard"):
                client.create_heat_intelligence_request(sample_heat_intelligence_request())
        finally:
            client.close()

    def test_timeout_raises_transport_error(self) -> None:
        """Request timeout raises TransportError."""
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Read timed out")

        client = make_client(handler)
        try:
            with pytest.raises(TransportError):
                client.create_heat_intelligence_request(sample_heat_intelligence_request())
        finally:
            client.close()

    def test_dns_resolution_failure(self) -> None:
        """DNS resolution failure is caught as TransportError."""
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Name or service not known")

        client = make_client(handler)
        try:
            with pytest.raises(TransportError):
                client.get_activity_status("act-dns-fail")
        finally:
            client.close()


# ══════════════════════════════════════════════════════════════════════════════
# Section 4: Polling Timeout & Recovery
# ══════════════════════════════════════════════════════════════════════════════


class TestPollingFailures:
    """Verify polling timeout detection and recovery."""

    def test_polling_timeout_after_max_attempts(self) -> None:
        """Polling that never reaches Completed/Failed raises PollingTimeoutError."""
        call_count = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=status_payload("act-stuck", status="Processing"))

        client = make_client(handler)
        try:
            with pytest.raises(PollingTimeoutError) as exc_info:
                client.poll_heatmap_result("act-stuck", max_attempts=3, poll_interval_seconds=0.01)
            assert exc_info.value.activity_id == "act-stuck"
            assert call_count == 3
        finally:
            client.close()

    def test_polling_succeeds_on_last_attempt(self) -> None:
        """Polling succeeds when Completed status arrives on the final attempt."""
        call_count = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return httpx.Response(200, json=status_payload("act-late", status="Processing"))
            return httpx.Response(200, json=status_payload("act-late", status="Completed", result={"data": "ok"}))

        client = make_client(handler)
        try:
            result = client.poll_heatmap_result("act-late", max_attempts=3, poll_interval_seconds=0.01)
            assert result.status == "Completed"
            assert call_count == 3
        finally:
            client.close()

    def test_polling_failed_status_stops_immediately(self) -> None:
        """Polling stops immediately when status transitions to Failed."""
        call_count = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return httpx.Response(200, json=status_payload("act-fail", status="Processing"))
            return httpx.Response(200, json=status_payload("act-fail", status="Failed"))

        client = make_client(handler)
        try:
            result = client.poll_heatmap_result("act-fail", max_attempts=10, poll_interval_seconds=0.01)
            assert result.status == "Failed"
            assert call_count == 2
        finally:
            client.close()

    def test_polling_with_zero_max_attempts_raises(self) -> None:
        """max_attempts < 1 raises ValueError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=status_payload("act-001"))

        client = make_client(handler)
        try:
            with pytest.raises(ValueError, match="max_attempts"):
                client.poll_heatmap_result("act-001", max_attempts=0)
        finally:
            client.close()


# ══════════════════════════════════════════════════════════════════════════════
# Section 5: Failure Diagnostic Sanitization
# ══════════════════════════════════════════════════════════════════════════════


class TestDiagnosticSanitization:
    """Verify credentials are recursively stripped from failure diagnostics."""

    def test_failed_status_strips_api_key(self) -> None:
        """api_key fields are removed from failure diagnostic output."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {
                    "activity_id": "act-sanitize",
                    "status": "Failed",
                    "message": "Processing error",
                    "api_key": "sk-secret-123456",
                },
            })

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-sanitize")
            assert result.status == "Failed"
            assert result.diagnostic is not None
            diag_str = json.dumps(result.diagnostic)
            assert "sk-secret-123456" not in diag_str
            assert "api_key" not in diag_str
        finally:
            client.close()

    def test_failed_status_strips_token_fields(self) -> None:
        """token / authorization fields are removed from diagnostics."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {
                    "activity_id": "act-tok",
                    "status": "Failed",
                    "token": "eyJ...",
                    "authorization": "Bearer abc",
                },
            })

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-tok")
            diag_str = json.dumps(result.diagnostic) if result.diagnostic else ""
            assert "eyJ" not in diag_str
            assert "Bearer" not in diag_str
        finally:
            client.close()

    def test_failed_status_strips_signed_urls(self) -> None:
        """signed_url and X-Amz-Signature URLs are redacted."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {
                    "activity_id": "act-signed",
                    "status": "Failed",
                    "message": "Something failed",
                    "report_url": "https://s3.amazonaws.com/bucket/key?X-Amz-Signature=abc123",
                },
            })

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-signed")
            diag_str = json.dumps(result.diagnostic) if result.diagnostic else ""
            assert "X-Amz-Signature" not in diag_str
        finally:
            client.close()

    def test_nested_credential_redaction(self) -> None:
        """Nested structures with credential keys are recursively stripped."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {
                    "activity_id": "act-nested",
                    "status": "Failed",
                    "details": {
                        "info": "something",
                        "secret": "my-secret-val",
                        "nested": {"password": "pass123", "safe": "ok"},
                    },
                },
            })

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-nested")
            diag_str = json.dumps(result.diagnostic) if result.diagnostic else ""
            assert "my-secret-val" not in diag_str
            assert "pass123" not in diag_str
        finally:
            client.close()


# ══════════════════════════════════════════════════════════════════════════════
# Section 6: NaN / Inf / None Metric Resilience
# ══════════════════════════════════════════════════════════════════════════════


class TestMetricEdgeCases:
    """Verify intelligence pipeline handles NaN, Inf, None, and missing metrics."""

    def test_nan_metrics_do_not_crash_pipeline(self) -> None:
        """Records with NaN metrics do not crash the signal pipeline."""
        rec = _make_record(1, metrics={"mean_temp": float("nan"), "temp_spread": 10.0, "total_tiles": 80})
        clk = FrozenClock("2026-08-23T12:00:00Z")
        # Should not raise
        signals = generate_pipeline_signals([rec], clock=clk)
        assert isinstance(signals, list)

    def test_inf_metrics_do_not_crash_pipeline(self) -> None:
        """Records with Inf metrics do not crash the signal pipeline."""
        rec = _make_record(2, metrics={"mean_temp": float("inf"), "temp_spread": 10.0, "total_tiles": 80})
        clk = FrozenClock("2026-08-23T12:00:00Z")
        signals = generate_pipeline_signals([rec], clock=clk)
        assert isinstance(signals, list)

    def test_none_metrics_do_not_crash_pipeline(self) -> None:
        """Records with None metric values do not crash the signal pipeline."""
        rec = _make_record(3, metrics={"mean_temp": None, "temp_spread": None, "total_tiles": None})
        clk = FrozenClock("2026-08-23T12:00:00Z")
        signals = generate_pipeline_signals([rec], clock=clk)
        assert isinstance(signals, list)

    def test_empty_metrics_dict(self) -> None:
        """Records with empty metrics dict do not crash the pipeline."""
        rec = _make_record(4, metrics={})
        clk = FrozenClock("2026-08-23T12:00:00Z")
        signals = generate_pipeline_signals([rec], clock=clk)
        assert isinstance(signals, list)

    def test_negative_inf_metrics(self) -> None:
        """Negative infinity in metrics does not crash the pipeline."""
        rec = _make_record(5, metrics={"mean_temp": float("-inf"), "temp_spread": 10.0, "total_tiles": 80})
        clk = FrozenClock("2026-08-23T12:00:00Z")
        signals = generate_pipeline_signals([rec], clock=clk)
        assert isinstance(signals, list)

    def test_string_metrics_are_handled(self) -> None:
        """String values in numeric metric fields do not crash the pipeline."""
        rec = _make_record(6, metrics={"mean_temp": "not_a_number", "temp_spread": "hot", "total_tiles": 80})
        clk = FrozenClock("2026-08-23T12:00:00Z")
        signals = generate_pipeline_signals([rec], clock=clk)
        assert isinstance(signals, list)


# ══════════════════════════════════════════════════════════════════════════════
# Section 7: Orchestrator Resilience to Garbage Inputs
# ══════════════════════════════════════════════════════════════════════════════


class TestOrchestratorResilience:
    """Verify Phase 15 orchestrator handles edge-case inputs gracefully."""

    def test_empty_records_produces_valid_snapshot(self) -> None:
        """Empty record list produces a valid snapshot with zero signals."""
        clk = FrozenClock("2026-08-23T12:00:00Z")
        snap = run_phase15_intelligence([], clock=clk)
        assert snap.diagnostics_summary["analyses_evaluated"] == 0
        assert len(snap.signals) == 0

    def test_single_record_with_extreme_values(self) -> None:
        """Extreme metric values produce a valid snapshot."""
        rec = _make_record(10, metrics={"mean_temp": 999.99, "temp_spread": 500.0, "total_tiles": 10000})
        clk = FrozenClock("2026-08-23T12:00:00Z")
        snap = run_phase15_intelligence([rec], clock=clk)
        assert snap.diagnostics_summary["analyses_evaluated"] == 1

    def test_duplicate_analysis_ids_in_input(self) -> None:
        """Duplicate analysis_id records do not crash the orchestrator."""
        rec1 = _make_record(11)
        rec2 = _make_record(11)  # Same ID
        clk = FrozenClock("2026-08-23T12:00:00Z")
        # Should not raise
        snap = run_phase15_intelligence([rec1, rec2], clock=clk)
        assert snap is not None


# ══════════════════════════════════════════════════════════════════════════════
# Section 8: Evidence Bundle Edge Cases
# ══════════════════════════════════════════════════════════════════════════════


class TestEvidenceBundleEdgeCases:
    """Verify evidence bundle construction handles edge cases."""

    def test_evidence_bundle_with_missing_metric(self) -> None:
        """Signal without standard metric fields still produces a valid bundle."""
        sig = {
            "signal_id": "SIG-EDGE-01",
            "analysis_id": "EDGE-001",
            "title": "Edge case signal",
        }
        clk = FrozenClock("2026-08-23T12:00:00Z")
        bundle = build_evidence_bundle(sig, clock=clk)
        assert bundle.target_id == "SIG-EDGE-01"
        assert bundle.evidence_hash

    def test_evidence_bundle_with_empty_record(self) -> None:
        """Evidence bundle with an empty AnalysisRecord metric set."""
        sig = {"signal_id": "SIG-EDGE-02", "analysis_id": "EDGE-002"}
        rec = _make_record(20, metrics={})
        clk = FrozenClock("2026-08-23T12:00:00Z")
        bundle = build_evidence_bundle(sig, analysis_record=rec, clock=clk)
        assert bundle is not None
        assert bundle.evidence_hash

    def test_evidence_hash_determinism(self) -> None:
        """Same inputs always produce the same evidence hash."""
        items = [{"metric": "mean_temp", "observed_value": 42.5}]
        h1 = calculate_evidence_hash("SIG-DET-01", "ANA-DET-01", items)
        h2 = calculate_evidence_hash("SIG-DET-01", "ANA-DET-01", items)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest length

    def test_evidence_hash_changes_with_different_inputs(self) -> None:
        """Different inputs produce different hashes."""
        items1 = [{"metric": "mean_temp", "observed_value": 42.5}]
        items2 = [{"metric": "mean_temp", "observed_value": 43.0}]
        h1 = calculate_evidence_hash("SIG-DIF-01", "ANA-DIF-01", items1)
        h2 = calculate_evidence_hash("SIG-DIF-01", "ANA-DIF-01", items2)
        assert h1 != h2


# ══════════════════════════════════════════════════════════════════════════════
# Section 9: Unicode / Special Character Injection
# ══════════════════════════════════════════════════════════════════════════════


class TestUnicodeInjection:
    """Verify system handles Unicode and special characters safely."""

    def test_unicode_location_label(self) -> None:
        """Unicode characters in location_label do not crash the pipeline."""
        rec = _make_record(30)
        rec.location_label = "東京都渋谷区 / مدينة الرياض"
        clk = FrozenClock("2026-08-23T12:00:00Z")
        snap = run_phase15_intelligence([rec], clock=clk)
        assert snap is not None

    def test_unicode_in_summary(self) -> None:
        """Unicode in summary field is preserved."""
        rec = _make_record(31)
        rec.summary = "Análisis de calor 🌡️ — données de température très élevée"
        clk = FrozenClock("2026-08-23T12:00:00Z")
        snap = run_phase15_intelligence([rec], clock=clk)
        assert snap.diagnostics_summary["analyses_evaluated"] == 1

    def test_null_byte_in_activity_id_handled(self) -> None:
        """Null bytes in activity_id are handled without crashes."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=submission_payload("act\x00ivity"))

        client = make_client(handler)
        try:
            result = client.create_heat_intelligence_request(sample_heat_intelligence_request())
            assert result.activity_id  # Non-empty
        finally:
            client.close()

    def test_html_injection_in_provider_message(self) -> None:
        """HTML/script injection in error messages is preserved as string, not executed."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "error": False,
                "data": {
                    "activity_id": "act-xss",
                    "status": "Failed",
                    "message": "<script>alert('xss')</script>",
                },
            })

        client = make_client(handler)
        try:
            result = client.get_activity_status("act-xss")
            assert result.status == "Failed"
            # Message should be preserved as raw string, not interpreted
            assert result.diagnostic is not None
            assert "<script>" in result.diagnostic.get("message", "")
        finally:
            client.close()


# ══════════════════════════════════════════════════════════════════════════════
# Section 10: Recovery After Transient Failure
# ══════════════════════════════════════════════════════════════════════════════


class TestRecoveryAfterFailure:
    """Verify the system recovers cleanly after transient provider failures."""

    def test_client_works_after_500_error(self) -> None:
        """Client can successfully submit after a prior 500 error."""
        call_count = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(500, json={"error": True, "message": "Temporary failure"})
            return httpx.Response(200, json=submission_payload("act-recovery"))

        client = make_client(handler)
        try:
            with pytest.raises(ServerError):
                client.create_heat_intelligence_request(sample_heat_intelligence_request())

            # Second call should succeed
            result = client.create_heat_intelligence_request(sample_heat_intelligence_request())
            assert result.activity_id == "act-recovery"
        finally:
            client.close()

    def test_client_works_after_transport_error(self) -> None:
        """Client recovers after a transport-level failure."""
        call_count = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("Transient network issue")
            return httpx.Response(200, json=submission_payload("act-net-recovery"))

        client = make_client(handler)
        try:
            with pytest.raises(TransportError):
                client.create_heat_intelligence_request(sample_heat_intelligence_request())

            result = client.create_heat_intelligence_request(sample_heat_intelligence_request())
            assert result.activity_id == "act-net-recovery"
        finally:
            client.close()

    def test_intelligence_pipeline_runs_after_bad_record(self) -> None:
        """Intelligence pipeline runs cleanly after processing a record with garbage metrics."""
        bad_rec = _make_record(50, metrics={"mean_temp": float("nan"), "total_tiles": None})
        good_rec = _make_record(51, metrics={"mean_temp": 42.0, "temp_spread": 8.0, "total_tiles": 100})
        clk = FrozenClock("2026-08-23T12:00:00Z")

        # Both records processed together
        snap = run_phase15_intelligence([bad_rec, good_rec], clock=clk)
        assert snap.diagnostics_summary["analyses_evaluated"] == 2

    def test_empty_activity_id_raises_value_error(self) -> None:
        """Empty string activity_id raises ValueError, not a network call."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=status_payload("anything"))

        client = make_client(handler)
        try:
            with pytest.raises(ValueError, match="activity_id"):
                client.get_activity_status("")
        finally:
            client.close()

    def test_whitespace_only_activity_id_raises_value_error(self) -> None:
        """Whitespace-only activity_id raises ValueError."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=status_payload("anything"))

        client = make_client(handler)
        try:
            with pytest.raises(ValueError, match="activity_id"):
                client.get_activity_status("   ")
        finally:
            client.close()
