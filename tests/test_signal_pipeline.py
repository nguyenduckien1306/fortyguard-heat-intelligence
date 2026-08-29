"""Unit tests for Phase 15.3 Signal Pipeline & Deterministic Deduplication.

Verifies:
- SHA-256 fingerprint generation determinism.
- Signal precedence ordering across the 6 supported signal types.
- Multiple independent signals vs. duplicate signal detection.
- SignalDisposition state transitions.
- Idempotent execution across repeated pipeline runs (0 -> 1 -> 1 -> 1).
- Zero network I/O.
"""

from __future__ import annotations

from unittest.mock import patch
import pytest
import streamlit as st

from frontend.utils.clock import FrozenClock, set_current_clock
from frontend.utils.signal_pipeline import (
    DISPOSITION_ACKNOWLEDGED,
    DISPOSITION_DISMISSED,
    DISPOSITION_LINKED_TO_ALERT,
    DISPOSITION_NEW,
    DISPOSITION_RESOLVED,
    SIGNAL_TYPE_DATA_ANOMALY,
    SIGNAL_TYPE_PRECEDENCE,
    SIGNAL_TYPE_RAPID_CHANGE,
    SIGNAL_TYPE_REPEATED_HEAT,
    SIGNAL_TYPE_SIGNIFICANT_CHANGE,
    SIGNAL_TYPE_THRESHOLD_BREACH,
    SIGNAL_TYPE_WATCHLIST_MATCH,
    SignalDisposition,
    detect_analysis_signals,
    detect_watchlist_signals,
    generate_pipeline_signals,
    generate_signal_fingerprint,
    get_signal_disposition,
    update_signal_disposition,
)
from frontend.utils.watchlist_engine import WatchlistEvaluation


class MockAnalysisRecord:
    """Mock AnalysisRecord for signal detection tests."""

    def __init__(
        self,
        analysis_id: str = "REC-01",
        analysis_type: str = "heatmap",
        location_label: str = "Downtown Core",
        date: str = "2026-08-20",
        created_at: str = "2026-08-20T10:00:00",
        metrics: dict | None = None,
        observed_temperature: float | None = None,
        status: str = "Completed",
    ):
        self.analysis_id = analysis_id
        self.analysis_type = analysis_type
        self.location_label = location_label
        self.date = date
        self.created_at = created_at
        self.metrics = dict(metrics) if metrics is not None else {}
        self.observed_temperature = observed_temperature
        self.status = status

    def to_dict(self) -> dict:
        return {
            "analysis_id": self.analysis_id,
            "analysis_type": self.analysis_type,
            "location_label": self.location_label,
            "date": self.date,
            "created_at": self.created_at,
            "metrics": dict(self.metrics),
            "observed_temperature": self.observed_temperature,
            "status": self.status,
        }


@pytest.fixture(autouse=True)
def clean_session():
    st.session_state.clear()
    set_current_clock(FrozenClock("2026-08-23T10:00:00"))
    yield
    st.session_state.clear()
    set_current_clock(None)


# ══════════════════════════════════════════════════════════════════════════════
# 1. SHA-256 Fingerprint Determinism Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestSignalFingerprinting:
    """Deterministic fingerprint generation tests."""

    def test_fingerprint_identical_for_same_identity(self):
        fp1 = generate_signal_fingerprint(
            signal_type=SIGNAL_TYPE_THRESHOLD_BREACH,
            analysis_id="REC-001",
            watchlist_id="WL-01",
            criterion_key="mean_temperature",
        )
        fp2 = generate_signal_fingerprint(
            signal_type=SIGNAL_TYPE_THRESHOLD_BREACH,
            analysis_id="REC-001",
            watchlist_id="WL-01",
            criterion_key="mean_temperature",
        )
        assert fp1 == fp2
        assert len(fp1) == 64

    def test_fingerprint_differs_by_signal_type(self):
        fp1 = generate_signal_fingerprint(SIGNAL_TYPE_THRESHOLD_BREACH, "REC-001")
        fp2 = generate_signal_fingerprint(SIGNAL_TYPE_RAPID_CHANGE, "REC-001")
        assert fp1 != fp2

    def test_fingerprint_differs_by_analysis_id(self):
        fp1 = generate_signal_fingerprint(SIGNAL_TYPE_THRESHOLD_BREACH, "REC-001")
        fp2 = generate_signal_fingerprint(SIGNAL_TYPE_THRESHOLD_BREACH, "REC-002")
        assert fp1 != fp2

    def test_fingerprint_differs_by_watchlist_id(self):
        fp1 = generate_signal_fingerprint(SIGNAL_TYPE_WATCHLIST_MATCH, "REC-001", watchlist_id="WL-01")
        fp2 = generate_signal_fingerprint(SIGNAL_TYPE_WATCHLIST_MATCH, "REC-001", watchlist_id="WL-02")
        assert fp1 != fp2

    def test_fingerprint_case_normalization(self):
        fp1 = generate_signal_fingerprint("threshold_breach", "REC-001", criterion_key="MEAN_TEMP")
        fp2 = generate_signal_fingerprint("THRESHOLD_BREACH", "REC-001", criterion_key="mean_temp")
        assert fp1 == fp2


# ══════════════════════════════════════════════════════════════════════════════
# 2. Signal Precedence & Detection Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestSignalPrecedenceAndDetection:
    """Precedence ordering and multi-signal generation."""

    def test_precedence_ordering(self):
        assert SIGNAL_TYPE_PRECEDENCE[SIGNAL_TYPE_WATCHLIST_MATCH] > SIGNAL_TYPE_PRECEDENCE[SIGNAL_TYPE_THRESHOLD_BREACH]
        assert SIGNAL_TYPE_PRECEDENCE[SIGNAL_TYPE_THRESHOLD_BREACH] > SIGNAL_TYPE_PRECEDENCE[SIGNAL_TYPE_RAPID_CHANGE]
        assert SIGNAL_TYPE_PRECEDENCE[SIGNAL_TYPE_RAPID_CHANGE] > SIGNAL_TYPE_PRECEDENCE[SIGNAL_TYPE_SIGNIFICANT_CHANGE]
        assert SIGNAL_TYPE_PRECEDENCE[SIGNAL_TYPE_SIGNIFICANT_CHANGE] > SIGNAL_TYPE_PRECEDENCE[SIGNAL_TYPE_REPEATED_HEAT]
        assert SIGNAL_TYPE_PRECEDENCE[SIGNAL_TYPE_REPEATED_HEAT] > SIGNAL_TYPE_PRECEDENCE[SIGNAL_TYPE_DATA_ANOMALY]

    def test_detect_watchlist_signals_from_matched_evaluation(self):
        mock_eval = WatchlistEvaluation(
            eval_id="EV-1",
            watchlist_id="WL-01",
            watchlist_name="Extreme Heat",
            watchlist_version=1,
            evaluated_at="2026-08-23T10:00:00",
            matched=True,
            matched_criteria=["mean_temperature"],
            comparison_analysis_id="REC-001",
            observed_values={"mean_temperature": 41.5},
            threshold_values={"mean_temperature": 38.0},
            data_quality="HIGH",
            evidence_list=["Observed mean temperature 41.50°C >= threshold 38.00°C."],
        )
        signals = detect_watchlist_signals([mock_eval])
        assert len(signals) == 1
        sig = signals[0]
        assert sig.signal_type == SIGNAL_TYPE_WATCHLIST_MATCH
        assert sig.severity == "CRITICAL"
        assert sig.analysis_id == "REC-001"
        assert "Extreme Heat" in sig.title

    def test_detect_watchlist_signals_ignores_unmatched_evaluation(self):
        mock_eval = WatchlistEvaluation(
            eval_id="EV-2",
            watchlist_id="WL-02",
            watchlist_name="Cooling Trend",
            watchlist_version=1,
            evaluated_at="2026-08-23T10:00:00",
            matched=False,
        )
        signals = detect_watchlist_signals([mock_eval])
        assert len(signals) == 0

    def test_detect_analysis_signals_generates_typed_signals(self):
        rec = MockAnalysisRecord(metrics={"mean_temp": 42.0, "temp_spread": 12.0})
        signals = detect_analysis_signals([rec])
        assert len(signals) >= 1
        sig_types = {s.signal_type for s in signals}
        assert SIGNAL_TYPE_THRESHOLD_BREACH in sig_types or SIGNAL_TYPE_RAPID_CHANGE in sig_types


# ══════════════════════════════════════════════════════════════════════════════
# 3. Signal Disposition State Machine Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestSignalDispositionStateMachine:
    """Disposition tracking (NEW, ACKNOWLEDGED, LINKED_TO_ALERT, RESOLVED, DISMISSED)."""

    def test_default_disposition_is_new(self):
        disp = get_signal_disposition("SIG-UNSEEN-001")
        assert disp.status == DISPOSITION_NEW
        assert disp.signal_id == "SIG-UNSEEN-001"

    def test_update_disposition_to_acknowledged(self):
        disp = update_signal_disposition("SIG-1", DISPOSITION_ACKNOWLEDGED, notes="Reviewed by analyst.")
        assert disp.status == DISPOSITION_ACKNOWLEDGED
        assert disp.notes == "Reviewed by analyst."

        fetched = get_signal_disposition("SIG-1")
        assert fetched.status == DISPOSITION_ACKNOWLEDGED

    def test_update_disposition_to_linked_to_alert(self):
        disp = update_signal_disposition("SIG-2", DISPOSITION_LINKED_TO_ALERT)
        assert disp.status == DISPOSITION_LINKED_TO_ALERT

    def test_update_disposition_to_resolved(self):
        disp = update_signal_disposition("SIG-3", DISPOSITION_RESOLVED, notes="Resolved.")
        assert disp.status == DISPOSITION_RESOLVED

    def test_update_disposition_to_dismissed(self):
        disp = update_signal_disposition("SIG-4", DISPOSITION_DISMISSED, notes="Dismissed false alarm.")
        assert disp.status == DISPOSITION_DISMISSED

    def test_invalid_disposition_defaults_to_new(self):
        disp = update_signal_disposition("SIG-5", "INVALID_STATUS")
        assert disp.status == DISPOSITION_NEW


# ══════════════════════════════════════════════════════════════════════════════
# 4. Pipeline Idempotency & Deduplication Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestPipelineIdempotencyAndDeduplication:
    """Ensure repeated runs are 100% idempotent without signal duplication."""

    def test_repeated_pipeline_runs_produce_same_signal_count(self):
        clk = FrozenClock("2026-08-23T10:00:00")
        recs = [MockAnalysisRecord(analysis_id="R-1", metrics={"mean_temp": 41.0, "temp_spread": 10.0})]

        run1 = generate_pipeline_signals(recs, clock=clk)
        run2 = generate_pipeline_signals(recs, clock=clk)
        run3 = generate_pipeline_signals(recs, clock=clk)

        assert len(run1) == len(run2) == len(run3)
        assert [s["signal_id"] for s in run1] == [s["signal_id"] for s in run2]

    def test_distinguishes_multiple_independent_signals_on_same_record(self):
        # Record has both high mean temp AND high spread -> produces distinct signals
        rec = MockAnalysisRecord(analysis_id="R-MULTI", metrics={"mean_temp": 42.0, "temp_spread": 14.0})
        signals = generate_pipeline_signals([rec])
        assert len(signals) >= 2
        sig_ids = [s["signal_id"] for s in signals]
        assert len(sig_ids) == len(set(sig_ids))  # All unique IDs

    @patch("httpx.Client.request")
    @patch("requests.request")
    def test_signal_pipeline_makes_zero_network_calls(self, mock_requests, mock_httpx):
        recs = [MockAnalysisRecord(metrics={"mean_temp": 39.0})]
        _ = generate_pipeline_signals(recs)

        mock_requests.assert_not_called()
        mock_httpx.assert_not_called()

    def test_signal_disposition_from_dict_defaults(self):
        disp = SignalDisposition.from_dict({})
        assert disp.signal_id == ""
        assert disp.status == DISPOSITION_NEW
        assert disp.notes == ""

    def test_pipeline_output_contains_disposition_and_rank(self):
        rec = MockAnalysisRecord(metrics={"mean_temp": 42.0})
        signals = generate_pipeline_signals([rec])
        assert len(signals) >= 1
        s = signals[0]
        assert "disposition" in s
        assert "precedence_rank" in s
        assert s["disposition"] == DISPOSITION_NEW

    def test_pipeline_preserves_previously_updated_disposition(self):
        rec = MockAnalysisRecord(analysis_id="R-DISP", metrics={"mean_temp": 44.0})
        signals = generate_pipeline_signals([rec])
        target_id = signals[0]["signal_id"]

        # Update disposition to ACKNOWLEDGED
        update_signal_disposition(target_id, DISPOSITION_ACKNOWLEDGED, notes="Investigated.")

        # Re-run pipeline on same record
        re_signals = generate_pipeline_signals([rec])
        re_target = [s for s in re_signals if s["signal_id"] == target_id][0]
        assert re_target["disposition"] == DISPOSITION_ACKNOWLEDGED
        assert re_target["disposition_notes"] == "Investigated."

    def test_watchlist_signals_precedence_above_analysis_signals(self):
        rec = MockAnalysisRecord(analysis_id="R-BOTH", metrics={"mean_temp": 42.0})
        wl_eval = WatchlistEvaluation(
            eval_id="EV-PREC",
            watchlist_id="WL-P",
            watchlist_name="Precedence Watch",
            watchlist_version=1,
            evaluated_at="2026-08-23T10:00:00",
            matched=True,
            matched_criteria=["mean_temperature"],
            comparison_analysis_id="R-BOTH",
            observed_values={"mean_temperature": 42.0},
            threshold_values={"mean_temperature": 38.0},
        )
        signals = generate_pipeline_signals([rec], watchlist_evaluations=[wl_eval])
        assert len(signals) >= 2
        # First signal in sorted output must be WATCHLIST_MATCH due to highest precedence (rank 6)
        assert signals[0]["signal_type"] == SIGNAL_TYPE_WATCHLIST_MATCH
        assert signals[0]["precedence_rank"] == 6

    def test_empty_record_list_produces_empty_signals(self):
        signals = generate_pipeline_signals([])
        assert signals == []

    def test_non_completed_records_ignored(self):
        rec_proc = MockAnalysisRecord(analysis_id="R-PROC", status="Processing")
        rec_fail = MockAnalysisRecord(analysis_id="R-FAIL", status="Failed")
        signals = generate_pipeline_signals([rec_proc, rec_fail])
        assert signals == []

