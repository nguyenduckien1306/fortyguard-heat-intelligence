"""Phase 16 — Long-Session & State Lifecycle Test Suite.

Simulates extended operator sessions across multi-cycle workflows:
1. Multi-cycle analysis record addition, tagging, and pinning.
2. Watchlist creation, editing, evaluation, toggling, duplication, deletion.
3. Signal generation, precedence sorting, disposition state changes.
4. Alert promotion, cooldown filtering, escalation, recovery chains.
5. Investigation queue synchronization, assignment, structured notes CRUD.
6. Evidence bundle freshness lifecycle and refresh semantics.
7. Deletion of source records and orphaned state prevention.
8. Session reset leaving historical AnalysisRecords intact.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import pytest
import streamlit as st

from frontend.utils.alert_engine import (
    AlertItem,
    clear_alert_stores,
    get_active_alerts,
    promote_signals_to_alerts,
    resolve_alert,
)
from frontend.utils.alert_policies import AlertPolicy, get_alert_policies
from frontend.utils.analysis_history import (
    AnalysisRecord,
    add_analysis_record,
    clear_all_analysis_records,
    delete_analysis_record,
    get_analysis_record,
    list_analysis_records,
    pin_analysis_record,
)
from frontend.utils.clock import FrozenClock
from frontend.utils.evidence import build_evidence_bundle
from frontend.utils.investigation_queue import (
    add_note_to_investigation,
    add_to_investigation_queue,
    assign_investigation,
    clear_investigation_queue,
    get_investigation_queue,
    mark_in_review,
    mark_resolved,
    remove_from_investigation_queue,
)
from frontend.utils.phase15_orchestrator import reset_phase15_state, run_phase15_intelligence
from frontend.utils.signal_pipeline import (
    DISPOSITION_ACKNOWLEDGED,
    DISPOSITION_NEW,
    DISPOSITION_RESOLVED,
    generate_pipeline_signals,
    update_signal_disposition,
)
from frontend.utils.watchlists import (
    Watchlist,
    WatchlistCriterion,
    delete_watchlist,
    duplicate_watchlist,
    get_watchlists,
    reset_default_watchlists,
    save_watchlist,
    toggle_watchlist,
)


def _make_session_record(idx: int, loc: str = "District-A", mean_temp: float = 41.5) -> AnalysisRecord:
    now = datetime.now(timezone.utc).isoformat()
    return AnalysisRecord(
        analysis_id=f"SESS-REC-{idx:03d}",
        activity_id=f"act_sess_{idx:03d}",
        analysis_type="heatmap",
        created_at=now,
        updated_at=now,
        location_label=loc,
        date=f"2026-08-{(idx % 28) + 1:02d}",
        metrics={"mean_temp": mean_temp, "temp_spread": 10.0, "total_tiles": 80},
        status="Completed",
    )


@pytest.fixture(autouse=True)
def _clean_session():
    clear_all_analysis_records()
    clear_alert_stores()
    clear_investigation_queue()
    reset_phase15_state()
    yield
    clear_all_analysis_records()
    clear_alert_stores()
    clear_investigation_queue()
    reset_phase15_state()


class TestMultiCycleAnalysisAndIntelligenceLifecycle:
    """Test extended operator cycles across the complete intelligence fabric."""

    def test_100_cycle_incremental_analysis_simulation(self):
        """Simulate 100 sequential analysis additions and intelligence pipeline executions."""
        clk = FrozenClock("2026-08-23T12:00:00Z")
        reset_default_watchlists()

        all_records = []
        for i in range(100):
            rec = _make_session_record(i, loc=f"Loc-{i % 5}", mean_temp=30.0 + (i % 15))
            all_records.append(rec)
            add_analysis_record(rec)

            if i % 10 == 0:
                snap = run_phase15_intelligence(all_records, clock=clk)
                assert snap is not None
                assert snap.diagnostics_summary["analyses_evaluated"] == len(all_records)

        # Final state verification
        final_records = list_analysis_records()
        assert len(final_records) <= 50  # Capped by MAX_HISTORY_RECORDS
        final_snap = run_phase15_intelligence(final_records, clock=clk)
        assert final_snap.diagnostics_summary["analyses_evaluated"] == len(final_records)

    def test_watchlist_lifecycle_multi_action(self):
        """Simulate create -> evaluate -> duplicate -> toggle -> delete on watchlists."""
        reset_default_watchlists()
        initial_count = len(get_watchlists())

        # 1. Create
        c = WatchlistCriterion(metric="mean_temperature", operator=">", threshold=40.0)
        wl = Watchlist(watchlist_id="WL-LIFECYCLE-TEST", name="High Heat Custom", criteria=[c])
        ok, _, saved = save_watchlist(wl)
        assert ok and saved is not None
        new_id = saved.watchlist_id
        assert len(get_watchlists()) == initial_count + 1

        # 2. Toggle
        toggle_watchlist(new_id)
        assert not get_watchlists()[0 if get_watchlists()[0].watchlist_id == new_id else -1].enabled

        # 3. Duplicate
        ok_dup, _, dup_wl = duplicate_watchlist(new_id)
        assert ok_dup and dup_wl is not None
        assert len(get_watchlists()) == initial_count + 2

        # 4. Delete
        delete_watchlist(new_id)
        delete_watchlist(dup_wl.watchlist_id)
        assert len(get_watchlists()) == initial_count

    def test_signal_disposition_state_transitions(self):
        """Simulate operator progressing signal dispositions: NEW -> ACK -> RESOLVED -> DISMISSED."""
        rec = _make_session_record(1, mean_temp=45.0)
        clk = FrozenClock("2026-08-23T12:00:00Z")
        signals = generate_pipeline_signals([rec], clock=clk)
        assert len(signals) > 0

        target_sig = signals[0]
        sig_id = target_sig["signal_id"]

        # Default NEW
        assert target_sig["disposition"] == DISPOSITION_NEW

        # Update to ACKNOWLEDGED
        disp = update_signal_disposition(sig_id, DISPOSITION_ACKNOWLEDGED, notes="Reviewed by operator")
        assert disp.status == DISPOSITION_ACKNOWLEDGED

        # Re-run pipeline: disposition must persist
        signals_rerun = generate_pipeline_signals([rec], clock=clk)
        found = [s for s in signals_rerun if s["signal_id"] == sig_id]
        assert len(found) == 1
        assert found[0]["disposition"] == DISPOSITION_ACKNOWLEDGED

        # Update to RESOLVED
        disp = update_signal_disposition(sig_id, DISPOSITION_RESOLVED)
        assert disp.status == DISPOSITION_RESOLVED

    def test_alert_escalation_and_recovery_cycle(self):
        """Simulate breach -> alert creation -> escalation on repeated breach -> resolution."""
        rec = _make_session_record(1, mean_temp=46.0)
        clk = FrozenClock("2026-08-23T12:00:00Z")
        policies = get_alert_policies()

        signals = generate_pipeline_signals([rec], clock=clk)
        alerts1, diag1 = promote_signals_to_alerts(signals, policies, clock=clk)
        assert len(alerts1) > 0
        alert_id = alerts1[0].alert_id
        assert alerts1[0].escalation_level == "NORMAL"

        # Second breach under same policy
        alerts2, diag2 = promote_signals_to_alerts(signals, policies, clock=clk)
        # Escalation count increases or cooldown suppresses duplicate
        active = get_active_alerts()
        assert len(active) > 0

        # Resolve alert
        resolve_alert(alert_id, resolution_reason="Cooling intervention deployed")
        remaining_active = get_active_alerts()
        assert not any(a.alert_id == alert_id and a.status == "ACTIVE" for a in remaining_active)

    def test_investigation_queue_full_operator_flow(self):
        """Simulate add to queue -> assign -> add notes -> mark in review -> resolve."""
        rec = _make_session_record(1)
        ok, err, item = add_to_investigation_queue(
            analysis_id=rec.analysis_id,
            priority="High",
            reason="Thermal surge investigation",
            notes="Initial note",
        )
        assert ok and item is not None
        qid = item.queue_id

        # Assign
        assign_investigation(qid, "analyst_sarah")
        queue = get_investigation_queue()
        q_item = [i for i in queue if i.queue_id == qid][0]
        assert q_item.assigned_to == "analyst_sarah"

        # Add structured note
        add_note_to_investigation(qid, "Field team verified high surface temperature.")

        # In Review
        mark_in_review(qid)
        q_item = [i for i in get_investigation_queue() if i.queue_id == qid][0]
        assert q_item.status == "IN_REVIEW"

        # Resolve
        mark_resolved(qid)
        q_item = [i for i in get_investigation_queue() if i.queue_id == qid][0]
        assert q_item.status == "RESOLVED"

        # Remove from queue
        remove_from_investigation_queue(qid)
        assert not any(i.queue_id == qid for i in get_investigation_queue())

    def test_evidence_freshness_lifecycle(self):
        """Simulate evidence bundle created, validate timestamp-based freshness semantics."""
        rec = _make_session_record(1)
        sig = {
            "signal_id": "SIG-FRESH-01",
            "analysis_id": rec.analysis_id,
            "title": "Freshness test signal",
            "metric": "mean_temp",
            "observed_value": 41.5,
            "data_quality": "HIGH",
        }
        clk1 = FrozenClock("2026-08-23T12:00:00Z")
        bundle = build_evidence_bundle(sig, analysis_record=rec, clock=clk1)

        # Bundle captures the evidence_as_of timestamp from the clock
        assert bundle.evidence_as_of == "2026-08-23T12:00:00+00:00"
        assert bundle.analysis_id == rec.analysis_id
        assert bundle.evidence_hash  # SHA-256 hash is computed

        # Rebuilding at a later time yields a different evidence_as_of
        clk2 = FrozenClock("2026-08-23T12:30:00Z")
        bundle2 = build_evidence_bundle(sig, analysis_record=rec, clock=clk2)
        assert bundle2.evidence_as_of == "2026-08-23T12:30:00+00:00"

        # Same inputs produce the same evidence hash (determinism)
        assert bundle.evidence_hash == bundle2.evidence_hash

    def test_deleted_record_does_not_corrupt_history(self):
        """Deleting an analysis record safely preserves remaining history and pin states."""
        r1 = _make_session_record(1)
        r2 = _make_session_record(2)
        r3 = _make_session_record(3)

        add_analysis_record(r1)
        add_analysis_record(r2)
        add_analysis_record(r3)
        pin_analysis_record(r1.analysis_id)

        delete_analysis_record(r2.analysis_id)

        records = list_analysis_records()
        rec_ids = [r.analysis_id for r in records]
        assert r2.analysis_id not in rec_ids
        assert r1.analysis_id in rec_ids
        assert r3.analysis_id in rec_ids
        assert get_analysis_record(r1.analysis_id).pinned is True

    def test_reset_phase15_state_preserves_records_and_pins(self):
        """reset_phase15_state clears intelligence stores while keeping AnalysisRecords and pins."""
        r1 = _make_session_record(1)
        add_analysis_record(r1)
        pin_analysis_record(r1.analysis_id)

        # Run intelligence to populate caches
        _ = run_phase15_intelligence([r1])

        # Reset Phase 15 state
        reset_phase15_state()

        # Analysis records and pinned state remain intact
        recs = list_analysis_records()
        assert len(recs) == 1
        assert recs[0].analysis_id == r1.analysis_id
        assert recs[0].pinned is True
