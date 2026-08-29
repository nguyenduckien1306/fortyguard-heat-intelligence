"""Unit tests for Phase 15.5 Evidence Bundle & "Why am I seeing this?" Engine.

Verifies:
- EvidenceBundle immutability and SHA-256 evidence hashing.
- Hash consistency across dict item order variations.
- Freshness evaluation comparing evidence_as_of against record timestamps.
- "Why am I seeing this?" explanation generation (non-causal, strictly factual).
- Evidence bundle refresh workflows.
- Zero network I/O.
"""

from __future__ import annotations

from unittest.mock import patch
import pytest

from frontend.utils.clock import FrozenClock, ManualClock
from frontend.utils.evidence import (
    EvidenceBundle,
    build_evidence_bundle,
    calculate_evidence_hash,
    generate_why_seeing_this_narrative,
    refresh_evidence_bundle,
    verify_evidence_freshness,
)


class MockRecord:
    """Mock record for evidence freshness tests."""

    def __init__(
        self,
        analysis_id: str = "REC-001",
        updated_at: str = "2026-08-23T10:00:00",
        metrics: dict | None = None,
    ):
        self.analysis_id = analysis_id
        self.updated_at = updated_at
        self.metrics = dict(metrics) if metrics is not None else {}

    def to_dict(self) -> dict:
        return {
            "analysis_id": self.analysis_id,
            "updated_at": self.updated_at,
            "metrics": dict(self.metrics),
        }


# ══════════════════════════════════════════════════════════════════════════════
# 1. Evidence Hash & Immutability Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestEvidenceHashAndImmutability:
    """Deterministic hash calculations and model immutability."""

    def test_evidence_hash_determinism(self):
        items = [{"metric": "mean_temp", "observed_value": 41.5, "threshold_value": 38.0}]
        h1 = calculate_evidence_hash("ALT-001", "REC-001", items)
        h2 = calculate_evidence_hash("ALT-001", "REC-001", items)
        assert h1 == h2
        assert len(h1) == 64

    def test_evidence_hash_invariant_to_item_insertion_order(self):
        item_a = {"metric": "a_metric", "observed_value": 10.0}
        item_b = {"metric": "b_metric", "observed_value": 20.0}

        h1 = calculate_evidence_hash("ALT-001", "REC-001", [item_a, item_b])
        h2 = calculate_evidence_hash("ALT-001", "REC-001", [item_b, item_a])
        assert h1 == h2

    def test_evidence_bundle_immutability(self):
        bundle = EvidenceBundle(
            evidence_id="EVD-123",
            target_id="ALT-123",
            analysis_id="REC-123",
            evidence_as_of="2026-08-23T10:00:00",
            items=(),
            why_am_i_seeing_this="Test narrative",
        )
        with pytest.raises(AttributeError):
            bundle.evidence_id = "MUTATED"  # type: ignore[misc]


# ══════════════════════════════════════════════════════════════════════════════
# 2. Build Evidence Bundle Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestBuildEvidenceBundle:
    """Building complete EvidenceBundle objects from entities."""

    def test_build_bundle_from_signal_dict(self):
        clk = FrozenClock("2026-08-23T12:00:00")
        sig = {
            "signal_id": "SIG-TEST",
            "analysis_id": "REC-TEST",
            "title": "Severe Heat",
            "evidence": ["Observed mean temperature 42.0°C >= 38.0°C."],
            "data_quality": "HIGH",
        }
        bundle = build_evidence_bundle(sig, clock=clk)
        assert bundle.target_id == "SIG-TEST"
        assert bundle.analysis_id == "REC-TEST"
        assert bundle.evidence_as_of == "2026-08-23T12:00:00"
        assert len(bundle.items) == 1
        assert len(bundle.evidence_hash) == 64
        assert "Triggering Facts" in bundle.why_am_i_seeing_this

    def test_build_bundle_extracts_from_record_when_no_evidence_strings(self):
        clk = FrozenClock("2026-08-23T12:00:00")
        rec = MockRecord(analysis_id="REC-MTR", metrics={"mean_temp": 39.5, "temp_spread": 9.0})
        sig = {"signal_id": "SIG-EMPTY", "analysis_id": "REC-MTR"}

        bundle = build_evidence_bundle(sig, analysis_record=rec, clock=clk)
        assert len(bundle.items) == 2
        metrics_found = {i["metric"] for i in bundle.items}
        assert "mean_temperature" in metrics_found
        assert "temperature_spread" in metrics_found


# ══════════════════════════════════════════════════════════════════════════════
# 3. Freshness & Refresh Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestEvidenceFreshnessAndRefresh:
    """Freshness verification and bundle regeneration."""

    def test_freshness_passes_when_record_is_older_than_bundle(self):
        bundle = EvidenceBundle(
            evidence_id="EVD-F",
            target_id="ALT-F",
            analysis_id="REC-F",
            evidence_as_of="2026-08-23T12:00:00",
            items=(),
            why_am_i_seeing_this="",
        )
        old_rec = MockRecord(analysis_id="REC-F", updated_at="2026-08-23T10:00:00")
        assert verify_evidence_freshness(bundle, old_rec) is True

    def test_freshness_fails_when_record_updated_after_bundle(self):
        bundle = EvidenceBundle(
            evidence_id="EVD-S",
            target_id="ALT-S",
            analysis_id="REC-S",
            evidence_as_of="2026-08-23T10:00:00",
            items=(),
            why_am_i_seeing_this="",
        )
        new_rec = MockRecord(analysis_id="REC-S", updated_at="2026-08-23T12:00:00")
        assert verify_evidence_freshness(bundle, new_rec) is False

    def test_refresh_evidence_bundle_updates_timestamp(self):
        clk = ManualClock("2026-08-23T10:00:00")
        bundle = EvidenceBundle(
            evidence_id="EVD-OLD",
            target_id="ALT-OLD",
            analysis_id="REC-OLD",
            evidence_as_of="2026-08-23T10:00:00",
            items=(),
            why_am_i_seeing_this="",
        )
        rec = MockRecord(analysis_id="REC-OLD", updated_at="2026-08-23T11:00:00", metrics={"mean_temp": 40.0})

        clk.advance(hours=2)  # Clock is now 12:00:00
        refreshed = refresh_evidence_bundle(bundle, rec, clock=clk)
        assert refreshed.evidence_as_of == "2026-08-23T12:00:00"
        assert verify_evidence_freshness(refreshed, rec, clock=clk) is True


# ══════════════════════════════════════════════════════════════════════════════
# 4. Responsible Analytics Narrative Verification
# ══════════════════════════════════════════════════════════════════════════════


class TestResponsibleAnalyticsInEvidence:
    """Ensure evidence narratives never contain forbidden causal or medical claims."""

    def test_why_seeing_this_strictly_non_causal(self):
        narrative = generate_why_seeing_this_narrative(
            target_id="ALT-NC",
            title="High Temp",
            analysis_id="REC-NC",
            evidence_items=["Observed mean temperature 39.0°C >= 35.0°C."],
            data_quality="HIGH",
        )
        forbidden = ["caused by", "due to", "because of", "hazard", "fatal", "predict", "forecast"]
        for word in forbidden:
            assert word not in narrative.lower()

    @patch("httpx.Client.request")
    @patch("requests.request")
    def test_evidence_operations_make_zero_network_calls(self, mock_requests, mock_httpx):
        sig = {"signal_id": "S1", "analysis_id": "R1", "evidence": ["fact 1"]}
        bundle = build_evidence_bundle(sig)
        rec = MockRecord(analysis_id="R1")
        verify_evidence_freshness(bundle, rec)
        refresh_evidence_bundle(bundle, rec)

        mock_requests.assert_not_called()
        mock_httpx.assert_not_called()
