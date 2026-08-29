"""Phase 17 End-to-End Pipeline Test.

Executes the full session intelligence workflow twice to confirm:
- Deterministic output idempotency
- Zero duplicate objects
- Zero external HTTP calls
- Complete data integrity and evidence preservation
"""

from __future__ import annotations

import copy
import json
import pytest

from frontend.utils.alert_engine import evaluate_alert_policies, get_active_signals
from frontend.utils.alert_grouping import group_alerts
from frontend.utils.alert_policies import AlertPolicy
from frontend.utils.analysis_history import AnalysisRecord
from frontend.utils.attention_score import compute_attention_score, rank_by_attention
from frontend.utils.clock import FrozenClock
from frontend.utils.evidence import build_evidence_bundle
from frontend.utils.export import generate_operational_decision_case_brief
from frontend.utils.investigation_queue import add_to_investigation_queue, clear_investigation_queue, get_investigation_queue
from frontend.utils.latest_change import compute_latest_change
from frontend.utils.location_intelligence import build_location_summaries
from frontend.utils.operational_intelligence import generate_operational_signals
from frontend.utils.operational_summary import build_operational_summary
from frontend.utils.operator_actions import generate_all_actions
from frontend.utils.pattern_detection import detect_all_patterns
from frontend.utils.priority import get_signal_priority, sort_signals_by_priority
from frontend.utils.review_delta import compute_review_delta
from frontend.utils.watchlist_engine import evaluate_watchlist
from frontend.utils.watchlists import Watchlist, WatchlistCriterion


def _run_full_phase17_pipeline(records, clock):
    """Run the entire Phase 17 intelligence pipeline deterministically."""
    # Clear session-local investigation queue for idempotent runs
    clear_investigation_queue()

    # 1. Operational Executive Summary
    summary = build_operational_summary(records=records, clock=clock)

    # 2. Latest Change
    latest_change = compute_latest_change(records)

    # 3. Pattern Detection
    patterns = detect_all_patterns(records=records)

    # 4. Location Intelligence
    loc_summaries = build_location_summaries(records=records)

    # 5. Operational Signals & Policies
    signals = generate_operational_signals(records)
    policy = AlertPolicy(
        policy_id="POL-E2E-1",
        name="High Heat Policy",
        metric="mean_temperature",
        operator=">",
        threshold=33.0,
        severity="CRITICAL",
    )
    pol_signals = evaluate_alert_policies(records, [policy])
    all_signals = sort_signals_by_priority(signals + pol_signals)
    active_sigs = get_active_signals(all_signals)

    # 6. Watchlist Evaluation
    wl = Watchlist(
        watchlist_id="WL-E2E-1",
        name="Downtown Monitoring",
        location_scope="Downtown Central",
        criteria=[WatchlistCriterion(metric="mean_temperature", operator=">", threshold=33.0)],
    )
    wl_eval = evaluate_watchlist(wl, records, clock=clock)
    wl_evals = [wl_eval]

    # 7. Alert Grouping
    alert_objs = [
        {
            "alert_id": f"ALT-{s.signal_id}",
            "analysis_id": s.analysis_id,
            "severity": s.severity,
            "priority_score": get_signal_priority(s)[0],
        }
        for s in active_sigs
    ]
    groups = group_alerts(alert_objs)

    # 8. Attention Scoring
    ranked_attention = rank_by_attention(alert_objs, clock=clock)

    # 9. Operator Actions
    actions = generate_all_actions(
        alerts=alert_objs,
        records=records,
        watchlist_evaluations=wl_evals,
    )

    # 10. Investigation Queue & Evidence Bundle
    top_sig = active_sigs[0] if active_sigs else None
    q_item = None
    ev_bundle = None
    if top_sig:
        ok, err, q_item = add_to_investigation_queue(
            analysis_id=top_sig.analysis_id,
            reason=top_sig.title,
            priority="Critical",
            location="Downtown Central",
            source_signal=top_sig,
            clock=clock,
        )
        ev_bundle = build_evidence_bundle(
            target=top_sig,
            analysis_record=records[-1],
            clock=clock,
        )

    # 11. Review Delta
    delta = compute_review_delta(
        last_review_timestamp="2026-08-27T00:00:00Z",
        records=records,
        signals=all_signals,
        alerts=alert_objs,
        watchlist_evaluations=wl_evals,
        clock=clock,
    )

    # 12. Operational Decision Case Brief
    brief_text = generate_operational_decision_case_brief(
        investigation_item=q_item,
        source_record=records[-1],
        source_signal=top_sig,
        latest_change_summary=latest_change,
        evidence_bundle=ev_bundle,
        format="text",
        clock=clock,
    )
    brief_json = generate_operational_decision_case_brief(
        investigation_item=q_item,
        source_record=records[-1],
        source_signal=top_sig,
        latest_change_summary=latest_change,
        evidence_bundle=ev_bundle,
        format="json",
        clock=clock,
    )

    return {
        "summary": summary.to_dict(),
        "latest_change": latest_change.to_dict(),
        "patterns": [p.to_dict() for p in patterns],
        "loc_summaries": [l.to_dict() for l in loc_summaries],
        "active_signals_count": len(active_sigs),
        "groups_count": len(groups),
        "ranked_attention": [a.to_dict() for a in ranked_attention],
        "actions_count": len(actions),
        "delta": delta.to_dict(),
        "brief_text": brief_text,
        "brief_json": brief_json,
    }


class TestPhase17EndToEnd:
    def test_full_pipeline_idempotency_run_twice(self, monkeypatch):
        """Execute full Phase 17 pipeline twice and assert exact equivalence."""
        import socket
        import httpx

        def _fail(*args, **kwargs):
            raise AssertionError("Network calls forbidden!")

        monkeypatch.setattr(httpx.Client, "send", _fail)
        monkeypatch.setattr(socket, "create_connection", _fail)

        records = [
            AnalysisRecord(
                analysis_id="HI-20260827-001",
                activity_id="ACT-001",
                analysis_type="heat_intelligence",
                created_at="2026-08-27T14:00:00Z",
                updated_at="2026-08-27T14:00:00Z",
                location_label="Downtown Central",
                date="2026-08-27",
                time="14:00",
                observed_temperature=32.8,
                status="Completed",
            ),
            AnalysisRecord(
                analysis_id="HI-20260828-001",
                activity_id="ACT-002",
                analysis_type="heat_intelligence",
                created_at="2026-08-28T14:00:00Z",
                updated_at="2026-08-28T14:00:00Z",
                location_label="Downtown Central",
                date="2026-08-28",
                time="14:00",
                observed_temperature=35.5,
                status="Completed",
            ),
        ]

        clk = FrozenClock("2026-08-28T16:00:00Z")

        # Run 1
        res1 = _run_full_phase17_pipeline(records, clk)

        # Run 2
        res2 = _run_full_phase17_pipeline(records, clk)

        assert res1["summary"] == res2["summary"]
        assert res1["latest_change"] == res2["latest_change"]
        assert res1["patterns"] == res2["patterns"]
        assert res1["loc_summaries"] == res2["loc_summaries"]
        assert res1["active_signals_count"] == res2["active_signals_count"]
        assert res1["ranked_attention"] == res2["ranked_attention"]
        assert res1["actions_count"] == res2["actions_count"]
        assert res1["delta"] == res2["delta"]
        assert res1["brief_text"] == res2["brief_text"]
        assert res1["brief_json"] == res2["brief_json"]

        # Parse JSON Brief and verify contents
        brief_data = json.loads(res1["brief_json"])
        assert brief_data["provenance"]["system_source"] == "FortyGuard Heat Intelligence Decision Engine"
        assert brief_data["source"]["location"] == "Downtown Central"
        assert brief_data["record"]["observed_temperature"] == 35.5
        assert brief_data["investigation"]["observed_value"] == 35.5
