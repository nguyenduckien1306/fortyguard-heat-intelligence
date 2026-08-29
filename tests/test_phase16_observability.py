"""Phase 16 — Structured Observability & Audit Event Logging Test Suite.

Verifies:
1. Structured event generation across all canonical lifecycle and intelligence stages.
2. Injectable Clock support for deterministic timestamps.
3. Strict recursive secret and signed URL redaction.
4. Bounded FIFO session buffer (capped at MAX_OBSERVABILITY_EVENTS).
5. Querying and filtering by event_name, analysis_id, and status.
6. Zero network I/O across all logging operations.
"""

from __future__ import annotations

from unittest.mock import patch
import pytest
import streamlit as st

from frontend.utils.clock import FrozenClock
from frontend.utils.observability import (
    EVENT_ALERT_COOLDOWN,
    EVENT_ALERT_PROMOTED,
    EVENT_ALERT_SUPPRESSED,
    EVENT_ANALYSIS_FAILED,
    EVENT_ANALYSIS_POLL_COMPLETED,
    EVENT_ANALYSIS_POLL_STARTED,
    EVENT_ANALYSIS_RETRY,
    EVENT_ANALYSIS_SUBMITTED,
    EVENT_ANALYSIS_TIMEOUT,
    EVENT_EVIDENCE_GENERATED,
    EVENT_EXPORT_GENERATED,
    EVENT_INVESTIGATION_CREATED,
    EVENT_SIGNAL_DEDUPLICATED,
    EVENT_SIGNAL_GENERATED,
    EVENT_WATCHLIST_EVALUATED,
    MAX_OBSERVABILITY_EVENTS,
    VALID_EVENT_NAMES,
    ObservabilityEvent,
    clear_observability_events,
    get_observability_events,
    record_event,
    sanitize_observability_data,
)


@pytest.fixture(autouse=True)
def _clean_obs_state():
    """Reset session state before each test."""
    clear_observability_events()
    yield
    clear_observability_events()


class TestCanonicalEventDefinitions:
    """Test standard event identifiers and definitions."""

    def test_all_canonical_events_defined(self):
        """Ensure all 15 core lifecycle event constants exist in VALID_EVENT_NAMES."""
        expected = [
            "analysis_submitted",
            "analysis_poll_started",
            "analysis_poll_completed",
            "analysis_failed",
            "analysis_timeout",
            "analysis_retry",
            "watchlist_evaluated",
            "signal_generated",
            "signal_deduplicated",
            "alert_promoted",
            "alert_suppressed",
            "alert_cooldown",
            "investigation_created",
            "evidence_generated",
            "export_generated",
        ]
        for ev in expected:
            assert ev in VALID_EVENT_NAMES


class TestEventRecordingAndClock:
    """Test recording events with deterministic clock and metadata."""

    def test_record_basic_event(self):
        """Record a basic event and verify stored properties."""
        clk = FrozenClock("2026-08-23T12:00:00Z")
        ev = record_event(
            event_name=EVENT_ANALYSIS_SUBMITTED,
            analysis_id="HM-001",
            activity_id="act_99",
            duration_ms=145.5,
            status="SUCCESS",
            clock=clk,
        )
        assert ev.event_name == EVENT_ANALYSIS_SUBMITTED
        assert "2026-08-23T12:00:00" in ev.timestamp
        assert ev.analysis_id == "HM-001"
        assert ev.activity_id == "act_99"
        assert ev.duration_ms == 145.5
        assert ev.status == "SUCCESS"

    def test_event_to_dict_and_from_dict_roundtrip(self):
        """ObservabilityEvent serializes to dict and restores accurately."""
        ev = ObservabilityEvent(
            event_name=EVENT_ALERT_PROMOTED,
            timestamp="2026-08-23T12:00:00Z",
            analysis_id="HM-002",
            status="SUCCESS",
            metadata={"priority": "Critical"},
        )
        d = ev.to_dict()
        restored = ObservabilityEvent.from_dict(d)
        assert restored.event_name == ev.event_name
        assert restored.timestamp == ev.timestamp
        assert restored.metadata == ev.metadata


class TestRecursiveSecretSanitization:
    """Test recursive redaction of credentials in event metadata."""

    def test_sanitize_plain_api_key(self):
        """Direct API key fields are redacted."""
        meta = {"api_key": "secret_key_123", "user": "operator"}
        clean = sanitize_observability_data(meta)
        assert clean["api_key"] == "[REDACTED]"
        assert clean["user"] == "operator"

    def test_sanitize_nested_tokens_and_bearer(self):
        """Deeply nested tokens and bearer strings are redacted."""
        meta = {
            "level1": {
                "level2": {
                    "token": "bearer_abc_999",
                    "password": "pass",
                    "safe_value": 42.5,
                }
            }
        }
        clean = sanitize_observability_data(meta)
        assert clean["level1"]["level2"]["token"] == "[REDACTED]"
        assert clean["level1"]["level2"]["password"] == "[REDACTED]"
        assert clean["level1"]["level2"]["safe_value"] == 42.5

    def test_sanitize_signed_s3_urls(self):
        """Signed S3 URLs containing X-Amz-Signature are redacted."""
        url = "https://s3.amazonaws.com/heatmaps/tiles.bin?X-Amz-Signature=abcdef123456"
        clean = sanitize_observability_data({"download_url": url})
        assert "X-Amz-Signature" not in str(clean)

    def test_record_event_automatically_sanitizes_metadata(self):
        """record_event auto-sanitizes any metadata passed in."""
        ev = record_event(
            event_name=EVENT_EXPORT_GENERATED,
            metadata={"secret_token": "sk-leak-test-1234", "export_type": "BRIEF"},
        )
        assert ev.metadata["secret_token"] == "[REDACTED]"
        assert ev.metadata["export_type"] == "BRIEF"


class TestBufferCapacityAndQueries:
    """Test bounded FIFO capacity and event querying."""

    def test_fifo_capacity_rotation_at_max_events(self):
        """Buffer automatically discards oldest events when exceeding capacity."""
        # Fill buffer past limit
        for i in range(MAX_OBSERVABILITY_EVENTS + 15):
            record_event(event_name=f"event_{i}")

        stored = get_observability_events(limit=1000)
        assert len(stored) == MAX_OBSERVABILITY_EVENTS
        # Oldest events 0-14 discarded, newest event is MAX + 14
        assert stored[-1].event_name == f"event_{MAX_OBSERVABILITY_EVENTS + 14}"

    def test_query_filter_by_event_name(self):
        """get_observability_events filters by event_name accurately."""
        record_event(event_name=EVENT_ANALYSIS_SUBMITTED, analysis_id="A-1")
        record_event(event_name=EVENT_WATCHLIST_EVALUATED, analysis_id="A-1")
        record_event(event_name=EVENT_ANALYSIS_SUBMITTED, analysis_id="A-2")

        sub_events = get_observability_events(event_name=EVENT_ANALYSIS_SUBMITTED)
        assert len(sub_events) == 2
        assert all(e.event_name == EVENT_ANALYSIS_SUBMITTED for e in sub_events)

    def test_query_filter_by_analysis_id(self):
        """get_observability_events filters by analysis_id."""
        record_event(event_name=EVENT_ANALYSIS_SUBMITTED, analysis_id="HM-TARGET")
        record_event(event_name=EVENT_ANALYSIS_SUBMITTED, analysis_id="HM-OTHER")

        events = get_observability_events(analysis_id="HM-TARGET")
        assert len(events) == 1
        assert events[0].analysis_id == "HM-TARGET"

    def test_clear_observability_events(self):
        """clear_observability_events removes all entries from session state."""
        record_event(event_name=EVENT_ANALYSIS_SUBMITTED)
        assert len(get_observability_events()) == 1
        clear_observability_events()
        assert len(get_observability_events()) == 0


class TestObservabilityZeroNetwork:
    """Test zero network I/O invariant during observability operations."""

    @patch("http.client.HTTPConnection.request")
    @patch("http.client.HTTPSConnection.request")
    @patch("urllib.request.urlopen")
    def test_observability_makes_zero_network_calls(
        self, mock_urlopen, mock_https, mock_http
    ):
        """Observability operations must never initiate network requests."""
        for ev_name in VALID_EVENT_NAMES:
            record_event(
                event_name=ev_name,
                analysis_id="HM-TEST",
                status="SUCCESS",
                metadata={"metric": "mean_temp", "val": 39.5},
            )

        events = get_observability_events(limit=50)
        assert len(events) == len(VALID_EVENT_NAMES)

        mock_http.assert_not_called()
        mock_https.assert_not_called()
        mock_urlopen.assert_not_called()


class TestObservabilityAdversarialCases:
    """Edge-case sanitization, empty inputs, and rerun-safe pipeline logging."""

    def test_sanitize_none_nan_and_empty_payloads(self):
        """None, empty collections, and numeric edge values are preserved safely."""
        import math

        clean = sanitize_observability_data(
            {"ok": None, "empty": {}, "list": [], "zero": 0, "nan": float("nan"), "inf": float("inf")}
        )
        assert clean["ok"] is None
        assert clean["empty"] == {}
        assert clean["list"] == []
        assert clean["zero"] == 0
        assert math.isnan(clean["nan"])
        assert math.isinf(clean["inf"])

    def test_sanitize_signature_query_and_unicode(self):
        """Generic Signature= query strings and unicode metadata are handled."""
        meta = {
            "title": "热浪 / موجة حر",
            "tile_url": "https://cdn.example.com/tile.bin?Signature=abc&Expires=1",
        }
        clean = sanitize_observability_data(meta)
        assert "Signature=" not in str(clean)
        assert "热浪" in clean["title"]

    def test_record_event_accepts_unknown_event_name(self):
        """Non-canonical event names still persist (forward compatible logging)."""
        ev = record_event(event_name="custom_operator_note", metadata={"note": "reviewed"})
        assert ev.event_name == "custom_operator_note"
        stored = get_observability_events()
        assert any(e.event_name == "custom_operator_note" for e in stored)

    def test_pipeline_observability_is_rerun_idempotent(self):
        """Identical orchestrator inputs do not duplicate observability events."""
        from frontend.utils.phase15_orchestrator import run_phase15_intelligence
        from frontend.utils.clock import FrozenClock

        clk = FrozenClock("2026-08-23T12:00:00Z")
        snap1 = run_phase15_intelligence([], clock=clk)
        first_count = len(get_observability_events(limit=500))
        snap2 = run_phase15_intelligence([], clock=clk)
        second_count = len(get_observability_events(limit=500))
        assert snap1.canonical_hash() == snap2.canonical_hash()
        assert second_count == first_count
