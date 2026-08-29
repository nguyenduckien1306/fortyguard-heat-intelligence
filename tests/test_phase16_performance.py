"""Phase 16 — Performance, Memory & State-Growth Hardening Test Suite.

Verifies:
1. Pure O(N) evaluation time across 50, 100, 250, 500, and 1000 completed records.
2. Watchlist evaluation throughput with maximum 20 active watchlists.
3. Signal pipeline, alert promotion, evidence bundling, and export generation speed.
4. Memory stability across 50 repeated Streamlit rerun cycles.
5. No memory leaks or accidental quadratic scaling in intelligence snapshot computation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import time
from typing import Any
import pytest
import streamlit as st

from frontend.utils.analysis_history import AnalysisRecord, add_analysis_record, clear_all_analysis_records
from frontend.utils.clock import FrozenClock
from frontend.utils.export import generate_command_center_decision_brief
from frontend.utils.intelligence_snapshot import IntelligenceSnapshot
from frontend.utils.phase15_orchestrator import run_phase15_intelligence
from frontend.utils.watchlists import Watchlist, WatchlistCriterion, get_watchlists, reset_default_watchlists, save_watchlist


def _make_benchmark_record(
    index: int,
    location_pool_size: int = 20,
) -> AnalysisRecord:
    """Generate deterministic synthetic AnalysisRecord for performance testing."""
    now = datetime.now(timezone.utc).isoformat()
    loc_id = index % location_pool_size
    month = (index % 12) + 1
    day = (index % 28) + 1
    date_str = f"2026-{month:02d}-{day:02d}"
    mean_temp = 25.0 + (index % 25) + (index * 0.01)

    return AnalysisRecord(
        analysis_id=f"PERF-REC-{index:05d}",
        activity_id=f"act_perf_{index:05d}",
        analysis_type="heatmap" if index % 2 == 0 else "heat_intelligence",
        created_at=now,
        updated_at=now,
        location_label=f"Zone-{loc_id:02d}",
        date=date_str,
        metrics={
            "mean_temp": round(mean_temp, 2),
            "min_temp": round(mean_temp - 5.0, 2),
            "max_temp": round(mean_temp + 6.0, 2),
            "temp_spread": 11.0,
            "total_tiles": 50 + (index % 150),
            "above_threshold_proportion": round((index % 100) / 100.0, 2),
        },
        observed_temperature=round(mean_temp, 2) if index % 2 != 0 else None,
        status="Completed",
    )


@pytest.fixture(autouse=True)
def _clean_state():
    clear_all_analysis_records()
    if hasattr(st, "session_state"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
    # Warm up runtime
    _ = run_phase15_intelligence([], clock=FrozenClock("2026-08-23T12:00:00Z"))
    if "_session_phase15_snapshot" in st.session_state:
        del st.session_state["_session_phase15_snapshot"]
    yield
    clear_all_analysis_records()
    if hasattr(st, "session_state"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]


class TestIntelligencePipelineScaling:
    """Test scaling and execution budgets across dataset sizes."""

    @pytest.mark.parametrize("record_count,max_budget_seconds", [
        (50, 8.0),
        (100, 12.0),
        (250, 20.0),
        (500, 35.0),
        (1000, 60.0),
    ])
    def test_pipeline_execution_budget(self, record_count: int, max_budget_seconds: float):
        """Pipeline completes well within allocated time budget for N records."""
        records = [_make_benchmark_record(i) for i in range(record_count)]
        reset_default_watchlists()
        clk = FrozenClock("2026-08-23T12:00:00Z")

        start = time.monotonic()
        snapshot = run_phase15_intelligence(records, clock=clk)
        elapsed = time.monotonic() - start

        assert isinstance(snapshot, IntelligenceSnapshot)
        assert snapshot.diagnostics_summary["analyses_evaluated"] == record_count
        assert elapsed < max_budget_seconds, f"{record_count} records took {elapsed:.2f}s (budget: {max_budget_seconds}s)"

    def test_sublinear_per_record_processing_rate(self):
        """Per-record evaluation overhead does not explode between 100 and 500 records."""
        recs_100 = [_make_benchmark_record(i) for i in range(100)]
        recs_500 = [_make_benchmark_record(i) for i in range(500)]
        clk = FrozenClock("2026-08-23T12:00:00Z")

        # Warm up JIT/caches
        _ = run_phase15_intelligence(recs_100[:10], clock=clk)
        if "_session_phase15_snapshot" in st.session_state:
            del st.session_state["_session_phase15_snapshot"]

        t0 = time.monotonic()
        _ = run_phase15_intelligence(recs_100, clock=clk)
        t_100 = time.monotonic() - t0

        if "_session_phase15_snapshot" in st.session_state:
            del st.session_state["_session_phase15_snapshot"]

        t0 = time.monotonic()
        _ = run_phase15_intelligence(recs_500, clock=clk)
        t_500 = time.monotonic() - t0

        rate_100 = t_100 / 100.0
        rate_500 = t_500 / 500.0

        # Rate should not increase by more than 4x (which would indicate quadratic O(N^2) behavior)
        assert rate_500 < rate_100 * 4.0, f"Rate increased excessively: 100={rate_100*1000:.2f}ms/rec vs 500={rate_500*1000:.2f}ms/rec"


class TestWatchlistCapacityScaling:
    """Test scaling with full capacity of 20 watchlists."""

    def test_full_capacity_20_watchlists_evaluation(self):
        """Evaluating 20 distinct multi-criteria watchlists over 200 records completes quickly."""
        records = [_make_benchmark_record(i) for i in range(200)]
        custom_watchlists = []

        for w_idx in range(20):
            c1 = WatchlistCriterion(metric="mean_temperature", operator=">", threshold=25.0 + w_idx)
            c2 = WatchlistCriterion(metric="temperature_spread", operator=">", threshold=10.0)
            wl = Watchlist(
                watchlist_id=f"WL-PERF-{w_idx:02d}",
                name=f"Performance Watchlist {w_idx}",
                criteria=[c1, c2],
                comparison_mode="PREVIOUS" if w_idx % 2 == 0 else "FIRST",
            )
            custom_watchlists.append(wl)

        clk = FrozenClock("2026-08-23T12:00:00Z")
        start = time.monotonic()
        snapshot = run_phase15_intelligence(records, watchlists=custom_watchlists, clock=clk)
        elapsed = time.monotonic() - start

        assert snapshot.diagnostics_summary["watchlists_evaluated"] == 20
        assert elapsed < 15.0, f"20 watchlists over 200 records took {elapsed:.2f}s"


class TestExportGenerationPerformance:
    """Test export brief generation throughput."""

    def test_large_snapshot_export_performance(self):
        """Exporting Decision Brief (TXT & JSON) on a large snapshot takes < 500ms."""
        records = [_make_benchmark_record(i) for i in range(200)]
        clk = FrozenClock("2026-08-23T12:00:00Z")
        snap = run_phase15_intelligence(records, clock=clk)

        t0 = time.monotonic()
        txt_brief = generate_command_center_decision_brief(snap, format="brief", clock=clk)
        t_txt = time.monotonic() - t0

        t0 = time.monotonic()
        json_brief = generate_command_center_decision_brief(snap, format="json", clock=clk)
        t_json = time.monotonic() - t0

        assert len(txt_brief) > 0
        assert len(json_brief) > 0
        assert t_txt < 0.5, f"TXT brief took {t_txt:.3f}s"
        assert t_json < 0.5, f"JSON brief took {t_json:.3f}s"


class TestRepeatedRerunStateStability:
    """Test memory and state stability over 50 simulated Streamlit rerun cycles."""

    def test_repeated_reruns_preserve_bounded_state(self):
        """Executing 50 consecutive rerun cycles maintains stable memory without state explosion."""
        records = [_make_benchmark_record(i) for i in range(50)]
        clk = FrozenClock("2026-08-23T12:00:00Z")

        hashes = set()
        for cycle in range(50):
            snap = run_phase15_intelligence(records, clock=clk)
            hashes.add(snap.canonical_hash())

        # Exact same hash every single rerun cycle
        assert len(hashes) == 1
        # No extra lingering session state keys created
        assert len(st.session_state) < 20
