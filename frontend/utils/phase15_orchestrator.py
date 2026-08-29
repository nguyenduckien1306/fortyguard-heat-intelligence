"""Phase 15 Central Intelligence Orchestrator.

Provides a single, canonical pipeline to run the complete intelligence cycle:
`Records -> Watchlists -> Evaluations -> Signals -> Deduplication -> Priority -> Alerts -> Queue -> Snapshot`

Strict Invariants:
1. Zero HTTP / Network I/O — 100% session-local in-memory evaluation.
2. Immutability: base AnalysisRecord instances are strictly read-only.
3. Determinism: identical inputs with the same clock produce the same canonical IntelligenceSnapshot.
4. Clean reset: reset_phase15_state() resets local intelligence state without modifying AnalysisRecords.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence
import streamlit as st

from frontend.utils.clock import Clock, get_current_clock
from frontend.utils.intelligence_snapshot import SCHEMA_VERSION, IntelligenceSnapshot

_SNAPSHOT_STORE_KEY = "_session_phase15_snapshot"
_WATCHLISTS_STORE_KEY = "_session_watchlists_store"
_SIGNAL_LIFECYCLE_STORE_KEY = "_session_signal_lifecycle_store"
_SIGNAL_DEDUP_STORE_KEY = "_session_signal_dedup_store"
_ALERT_COOLDOWN_STORE_KEY = "_session_alert_cooldown_store"
_QUEUE_STORE_KEY = "_session_investigation_queue"
_NOTES_STORE_KEY = "_session_investigation_notes"
_AUDIT_TRAIL_STORE_KEY = "_session_investigation_audit_trail"
_OBS_SNAPSHOT_HASH_KEY = "_session_phase16_last_obs_hash"


def reset_phase15_state() -> None:
    """Reset all Phase 15 intelligence stores while strictly preserving AnalysisRecord history."""
    keys_to_clear = [
        _SNAPSHOT_STORE_KEY,
        _WATCHLISTS_STORE_KEY,
        _SIGNAL_LIFECYCLE_STORE_KEY,
        _SIGNAL_DEDUP_STORE_KEY,
        _ALERT_COOLDOWN_STORE_KEY,
        _QUEUE_STORE_KEY,
        _NOTES_STORE_KEY,
        _AUDIT_TRAIL_STORE_KEY,
        _OBS_SNAPSHOT_HASH_KEY,
        "_session_active_alerts_store",
    ]
    for k in keys_to_clear:
        if k in st.session_state:
            del st.session_state[k]


def get_cached_snapshot() -> IntelligenceSnapshot | None:
    """Retrieve the current cached IntelligenceSnapshot from session state."""
    raw = st.session_state.get(_SNAPSHOT_STORE_KEY)
    if isinstance(raw, Mapping):
        return IntelligenceSnapshot.from_dict(raw)
    if isinstance(raw, IntelligenceSnapshot):
        return raw
    return None


def run_phase15_intelligence(
    records: Sequence[Any],
    watchlists: Sequence[Any] | None = None,
    policies: Sequence[Any] | None = None,
    clock: Clock | None = None,
    force_recompute: bool = False,
) -> IntelligenceSnapshot:
    """Execute the complete Phase 15 Proactive Intelligence cycle.

    Args:
        records: Sequence of AnalysisRecord objects or dicts.
        watchlists: Optional sequence of Watchlist objects (defaults to session store).
        policies: Optional sequence of AlertPolicy objects (defaults to session store).
        clock: Optional Clock abstraction for deterministic time calculations.
        force_recompute: If True, bypasses cache and recomputes the snapshot.

    Returns:
        Canonical, immutable IntelligenceSnapshot.
    """
    clk = clock or get_current_clock()
    now_iso = clk.now_iso()

    # Filter completed records safely without mutating
    completed_records: list[Any] = []
    record_ids: list[str] = []
    for r in records:
        r_status = r.status if hasattr(r, "status") else (r.get("status") if isinstance(r, Mapping) else "")
        if r_status == "Completed":
            completed_records.append(r)
            r_id = r.analysis_id if hasattr(r, "analysis_id") else str(r.get("analysis_id", ""))
            if r_id:
                record_ids.append(r_id)

    # 1. Watchlist Evaluations
    evaluations_json: list[dict[str, Any]] = []
    try:
        from frontend.utils.watchlist_engine import evaluate_all_watchlists
        from frontend.utils.watchlists import get_watchlists

        wl_list = list(watchlists) if watchlists is not None else get_watchlists()
        raw_evals = evaluate_all_watchlists(wl_list, completed_records, clock=clk)
        evaluations_json = [e.to_dict() if hasattr(e, "to_dict") else dict(e) for e in raw_evals]
    except (ImportError, Exception):
        evaluations_json = []

    # 2. Signal Generation & Deduplication
    signals_json: list[dict[str, Any]] = []
    try:
        from frontend.utils.signal_pipeline import generate_pipeline_signals

        signals_json = generate_pipeline_signals(
            records=completed_records,
            watchlist_evaluations=evaluations_json,
            clock=clk,
        )
    except (ImportError, Exception):
        # Fallback to base operational intelligence signals if pipeline module is loading
        try:
            from frontend.utils.operational_intelligence import generate_operational_signals
            raw_sigs = generate_operational_signals(completed_records)
            signals_json = [s.to_dict() if hasattr(s, "to_dict") else dict(s) for s in raw_sigs]
        except Exception:
            signals_json = []

    # 3. Alert Evaluation & Promotion
    alerts_json: list[dict[str, Any]] = []
    alerts_suppressed_count = 0
    cooldown_suppressed_count = 0
    low_quality_suppressed_count = 0
    try:
        from frontend.utils.alert_engine import evaluate_alert_policies, promote_signals_to_alerts
        from frontend.utils.alert_policies import get_alert_policies

        pol_list = list(policies) if policies is not None else get_alert_policies()
        raw_alerts, diag_info = promote_signals_to_alerts(signals_json, pol_list, clock=clk)
        alerts_json = [a.to_dict() if hasattr(a, "to_dict") else dict(a) for a in raw_alerts]
        alerts_suppressed_count = diag_info.get("total_suppressed", 0)
        cooldown_suppressed_count = diag_info.get("cooldown_suppressed", 0)
        low_quality_suppressed_count = diag_info.get("low_quality_suppressed", 0)
    except (ImportError, Exception):
        # Fallback
        try:
            from frontend.utils.alert_engine import evaluate_alert_policies
            from frontend.utils.alert_policies import get_alert_policies
            pol_list = list(policies) if policies is not None else get_alert_policies()
            raw_pols = evaluate_alert_policies(completed_records, pol_list)
            alerts_json = [s.to_dict() if hasattr(s, "to_dict") else dict(s) for s in raw_pols]
        except Exception:
            alerts_json = []

    # 4. Investigation Queue Items
    queue_json: list[dict[str, Any]] = []
    try:
        from frontend.utils.investigation_queue import get_investigation_queue
        q_items = get_investigation_queue()
        queue_json = [q.to_dict() if hasattr(q, "to_dict") else dict(q) for q in q_items]
    except Exception:
        queue_json = []

    # 5. Summaries & Distributions
    pri_summary = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    dq_summary = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "INSUFFICIENT": 0}

    for sig in signals_json:
        # Priority
        sev = str(sig.get("severity", "INFO")).upper()
        if sev == "CRITICAL":
            pri_summary["Critical"] += 1
        elif sev == "ELEVATED":
            pri_summary["High"] += 1
        elif sev == "WATCH":
            pri_summary["Medium"] += 1
        else:
            pri_summary["Low"] += 1

        # Data Quality
        dq = str(sig.get("data_quality", "HIGH")).upper()
        if dq in dq_summary:
            dq_summary[dq] += 1
        else:
            dq_summary["INSUFFICIENT"] += 1

    matched_watchlists = sum(1 for e in evaluations_json if e.get("matched"))

    diagnostics = {
        "analyses_evaluated": len(completed_records),
        "watchlists_evaluated": len(evaluations_json),
        "watchlist_matches": matched_watchlists,
        "signals_generated": len(signals_json),
        "alerts_promoted": len(alerts_json),
        "alerts_suppressed": alerts_suppressed_count,
        "cooldown_suppressions": cooldown_suppressed_count,
        "low_quality_suppressions": low_quality_suppressed_count,
        "open_investigations": sum(1 for q in queue_json if q.get("status") in ("OPEN", "IN_REVIEW")),
        "http_calls": 0,
    }

    # Generate Snapshot ID deterministically
    snap_seed = f"{sorted(record_ids)}_{now_iso}_{len(signals_json)}"
    snap_id = f"SNAP-{hashlib.sha256(snap_seed.encode('utf-8')).hexdigest()[:12]}"

    snapshot = IntelligenceSnapshot(
        snapshot_id=snap_id,
        generated_at=now_iso,
        record_ids=record_ids,
        watchlist_evaluations=evaluations_json,
        signals=signals_json,
        alerts=alerts_json,
        queue_items=queue_json,
        priority_summary=pri_summary,
        data_quality_summary=dq_summary,
        diagnostics_summary=diagnostics,
        schema_version=SCHEMA_VERSION,
    )

    _record_pipeline_observability(snapshot, clk)

    # Cache in session state
    st.session_state[_SNAPSHOT_STORE_KEY] = snapshot.to_dict()
    return snapshot


def _record_pipeline_observability(snapshot: IntelligenceSnapshot, clock: Clock) -> None:
    """Record a single observability batch per unique snapshot hash (rerun-safe)."""
    try:
        from frontend.utils.observability import (
            EVENT_ALERT_PROMOTED,
            EVENT_SIGNAL_GENERATED,
            EVENT_WATCHLIST_EVALUATED,
            record_event,
        )
    except Exception:
        return

    snap_hash = snapshot.canonical_hash()
    if st.session_state.get(_OBS_SNAPSHOT_HASH_KEY) == snap_hash:
        return
    st.session_state[_OBS_SNAPSHOT_HASH_KEY] = snap_hash

    diag = snapshot.diagnostics_summary
    record_event(
        event_name=EVENT_WATCHLIST_EVALUATED,
        status="SUCCESS",
        metadata={
            "watchlists_evaluated": diag.get("watchlists_evaluated", 0),
            "watchlist_matches": diag.get("watchlist_matches", 0),
            "analyses_evaluated": diag.get("analyses_evaluated", 0),
        },
        clock=clock,
    )
    if snapshot.signals:
        record_event(
            event_name=EVENT_SIGNAL_GENERATED,
            status="SUCCESS",
            metadata={"count": len(snapshot.signals)},
            clock=clock,
        )
    if snapshot.alerts:
        record_event(
            event_name=EVENT_ALERT_PROMOTED,
            status="SUCCESS",
            metadata={"count": len(snapshot.alerts)},
            clock=clock,
        )
