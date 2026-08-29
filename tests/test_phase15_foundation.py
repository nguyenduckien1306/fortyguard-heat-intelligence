"""Unit tests for Phase 15 Foundation Layer (Clock, IntelligenceSnapshot, Orchestrator).

Verifies:
- SystemClock, FrozenClock, and ManualClock behaviors.
- Deterministic timestamp generation and time advancement.
- IntelligenceSnapshot creation, dict roundtripping, and canonical hash calculation.
- Phase 15 Central Orchestrator execution, caching, and clean session reset.
- Zero network I/O and zero modification of AnalysisRecord history.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
import pytest
import streamlit as st

from frontend.utils.analysis_history import AnalysisRecord, add_analysis_record, clear_all_analysis_records, list_analysis_records
from frontend.utils.clock import (
    Clock,
    FrozenClock,
    ManualClock,
    SystemClock,
    get_current_clock,
    parse_timestamp_safe,
    set_current_clock,
)
from frontend.utils.intelligence_snapshot import SCHEMA_VERSION, IntelligenceSnapshot
from frontend.utils.phase15_orchestrator import (
    get_cached_snapshot,
    reset_phase15_state,
    run_phase15_intelligence,
)


@pytest.fixture(autouse=True)
def clean_environment():
    st.session_state.clear()
    set_current_clock(None)
    yield
    st.session_state.clear()
    set_current_clock(None)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Clock Abstraction Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestClockAbstraction:
    """Validate Clock implementations for deterministic testing."""

    def test_system_clock_returns_current_time(self):
        clk = SystemClock()
        t1 = clk.now()
        assert isinstance(t1, datetime)
        assert len(clk.now_iso()) >= 19
        assert clk.timestamp() > 0

    def test_frozen_clock_remains_static(self):
        fixed_str = "2026-08-23T12:00:00"
        clk = FrozenClock(fixed_str)
        assert clk.now_iso() == fixed_str
        assert clk.now() == datetime(2026, 8, 23, 12, 0, 0)
        assert clk.now() == clk.now()

    def test_manual_clock_advance(self):
        clk = ManualClock("2026-08-23T10:00:00")
        assert clk.now() == datetime(2026, 8, 23, 10, 0, 0)

        # Advance 15 minutes
        clk.advance(minutes=15)
        assert clk.now() == datetime(2026, 8, 23, 10, 15, 0)

        # Advance 2 hours and 30 seconds
        clk.advance(hours=2, seconds=30)
        assert clk.now() == datetime(2026, 8, 23, 12, 15, 30)

        # Set time explicitly
        clk.set_time("2026-08-24T00:00:00")
        assert clk.now() == datetime(2026, 8, 24, 0, 0, 0)

    def test_get_and_set_global_clock(self):
        custom_clk = FrozenClock("2026-08-23T14:30:00")
        set_current_clock(custom_clk)
        assert get_current_clock() is custom_clk
        assert get_current_clock().now_iso() == "2026-08-23T14:30:00"

        # Reset to SystemClock
        set_current_clock(None)
        assert isinstance(get_current_clock(), SystemClock)

    def test_parse_timestamp_safe(self):
        dt_target = datetime(2026, 8, 23, 10, 30, 0)
        assert parse_timestamp_safe(dt_target) == dt_target
        assert parse_timestamp_safe("2026-08-23T10:30:00") == dt_target
        assert parse_timestamp_safe("2026-08-23 10:30:00") == dt_target

        fallback = datetime(2026, 1, 1, 0, 0, 0)
        assert parse_timestamp_safe("invalid-date-string", default_time=fallback) == fallback
        assert parse_timestamp_safe(None, default_time=fallback) == fallback


# ══════════════════════════════════════════════════════════════════════════════
# 2. IntelligenceSnapshot Model Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestIntelligenceSnapshotModel:
    """Validate snapshot creation, hashing, and immutability."""

    def test_create_and_serialize_snapshot(self):
        snap = IntelligenceSnapshot(
            snapshot_id="SNAP-001",
            generated_at="2026-08-23T10:00:00",
            record_ids=["REC-1", "REC-2"],
            signals=[{"signal_id": "SIG-1", "severity": "CRITICAL"}],
            alerts=[{"alert_id": "ALT-1", "severity": "CRITICAL"}],
            queue_items=[{"queue_id": "Q-1", "status": "OPEN"}],
            priority_summary={"Critical": 1, "High": 0, "Medium": 0, "Low": 0},
            data_quality_summary={"HIGH": 1, "MEDIUM": 0, "LOW": 0, "INSUFFICIENT": 0},
            diagnostics_summary={"http_calls": 0},
        )

        d = snap.to_dict()
        assert d["snapshot_id"] == "SNAP-001"
        assert d["schema_version"] == SCHEMA_VERSION
        assert len(d["signals"]) == 1

        reconstructed = IntelligenceSnapshot.from_dict(d)
        assert reconstructed.snapshot_id == snap.snapshot_id
        assert reconstructed.record_ids == snap.record_ids
        assert reconstructed.canonical_hash() == snap.canonical_hash()

    def test_canonical_hash_determinism(self):
        snap1 = IntelligenceSnapshot(
            snapshot_id="SNAP-A",
            generated_at="2026-08-23T10:00:00",
            record_ids=["REC-B", "REC-A"],
            signals=[{"signal_id": "SIG-1"}],
        )
        snap2 = IntelligenceSnapshot(
            snapshot_id="SNAP-B",
            generated_at="2026-08-23T10:00:00",
            record_ids=["REC-A", "REC-B"],  # Order difference should produce identical canonical hash
            signals=[{"signal_id": "SIG-1"}],
        )
        assert snap1.canonical_hash() == snap2.canonical_hash()

    def test_snapshot_immutability(self):
        snap = IntelligenceSnapshot(
            snapshot_id="SNAP-IMMUTABLE",
            generated_at="2026-08-23T10:00:00",
            record_ids=["REC-1"],
        )
        with pytest.raises(AttributeError):
            snap.snapshot_id = "MUTATED"  # type: ignore[misc]


# ══════════════════════════════════════════════════════════════════════════════
# 3. Phase 15 Orchestrator Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestPhase15Orchestrator:
    """Validate single-cycle snapshot orchestration and clean reset."""

    def _sample_records(self) -> list[AnalysisRecord]:
        return [
            AnalysisRecord(
                analysis_id="HM-20260823-001",
                activity_id="act_001",
                analysis_type="heatmap",
                created_at="2026-08-23T10:00:00",
                updated_at="2026-08-23T10:00:00",
                location_label="Central Park",
                metrics={"mean_temp": 36.5, "temp_spread": 8.0, "total_tiles": 50},
                status="Completed",
            ),
            AnalysisRecord(
                analysis_id="HI-20260823-002",
                activity_id="act_002",
                analysis_type="heat_intelligence",
                created_at="2026-08-23T11:00:00",
                updated_at="2026-08-23T11:00:00",
                location_label="Midtown",
                observed_temperature=32.0,
                status="Completed",
            ),
        ]

    def test_run_phase15_intelligence_with_frozen_clock(self):
        clk = FrozenClock("2026-08-23T12:00:00")
        records = self._sample_records()

        snapshot = run_phase15_intelligence(records, clock=clk)
        assert isinstance(snapshot, IntelligenceSnapshot)
        assert snapshot.generated_at == "2026-08-23T12:00:00"
        assert len(snapshot.record_ids) == 2
        assert snapshot.diagnostics_summary["analyses_evaluated"] == 2
        assert snapshot.diagnostics_summary["http_calls"] == 0

        # Verify caching in session state
        cached = get_cached_snapshot()
        assert cached is not None
        assert cached.snapshot_id == snapshot.snapshot_id

    def test_reset_phase15_state_preserves_analysis_records(self):
        clear_all_analysis_records()
        for r in self._sample_records():
            add_analysis_record(r)

        # Set fake Phase 15 state
        st.session_state["_session_phase15_snapshot"] = {"snapshot_id": "SNAP-FAKE"}
        st.session_state["_session_watchlists_store"] = [{"watchlist_id": "WL-1"}]
        st.session_state["_session_investigation_queue"] = [{"queue_id": "Q-1"}]

        # Perform clean Phase 15 reset
        reset_phase15_state()

        # Phase 15 stores are cleared
        assert "_session_phase15_snapshot" not in st.session_state
        assert "_session_watchlists_store" not in st.session_state
        assert "_session_investigation_queue" not in st.session_state

        # AnalysisRecord history remains completely intact
        history = list_analysis_records()
        assert len(history) == 2
        history_ids = {r.analysis_id for r in history}
        assert "HM-20260823-001" in history_ids
        assert "HI-20260823-002" in history_ids

    @patch("httpx.Client.request")
    @patch("requests.request")
    def test_orchestrator_makes_zero_network_calls(self, mock_requests, mock_httpx):
        records = self._sample_records()
        clk = FrozenClock("2026-08-23T12:00:00")
        _ = run_phase15_intelligence(records, clock=clk)

        mock_requests.assert_not_called()
        mock_httpx.assert_not_called()
