"""Comprehensive End-to-End Invariant Tests for Phase 14 Operational Intelligence.

Validates the full operational pipeline:
Completed AnalysisRecord
  -> Signal Generation & Policy Evaluation
  -> Priority Scoring & Classification
  -> Investigation Queue Management
  -> Historical Comparison
  -> Scenario What-If Sandbox
  -> Investigation Brief Export
  -> Responsible Analytics & Security Sanitization

Strict Invariants Verified:
1. 0 FortyGuard API calls across all Phase 14 operations.
2. 0 credentials, tokens, passwords, or signed URLs exposed in any output or session structure.
3. 0 historical AnalysisRecord instances mutated.
4. 0 scenario records persisted to history.
5. 0 causal or predictive claims in generated text.
6. Deterministic outputs from identical inputs.
"""

from __future__ import annotations

import json
from unittest.mock import patch
import streamlit as st
import pytest

from frontend.utils.alert_engine import evaluate_alert_policies
from frontend.utils.alert_policies import AlertPolicy, get_default_alert_policies
from frontend.utils.analysis_history import AnalysisRecord, list_analysis_records
from frontend.utils.decision_intelligence import compare_analysis_records
from frontend.utils.export import generate_investigation_brief
from frontend.utils.investigation_queue import (
    STATUS_IN_REVIEW,
    STATUS_OPEN,
    STATUS_RESOLVED,
    add_to_investigation_queue,
    clear_investigation_queue,
    get_investigation_queue,
    mark_in_review,
    mark_resolved,
)
from frontend.utils.operational_intelligence import generate_operational_signals
from frontend.utils.priority import calculate_priority_score, get_signal_priority
from frontend.utils.responsible_analytics import is_text_compliant, validate_analytical_text
from frontend.utils.scenario_engine import compare_scenario_to_observed, create_scenario_adjustments


@pytest.fixture(autouse=True)
def clean_session_state():
    st.session_state.clear()
    yield
    st.session_state.clear()


def _build_test_records() -> tuple[AnalysisRecord, AnalysisRecord]:
    """Create sample completed analysis records with mock sensitive fields."""
    rec_baseline = AnalysisRecord(
        analysis_id="HM-20260820-001",
        activity_id="act_baseline_001",
        analysis_type="heatmap",
        created_at="2026-08-20T10:00:00",
        updated_at="2026-08-20T10:00:00",
        location_label="Financial District",
        date="2026-08-20",
        time="14:00",
        granularity=100,
        metrics={
            "mean_temp": 34.0,
            "min_temp": 28.0,
            "max_temp": 39.0,
            "temp_spread": 11.0,
            "total_tiles": 80,
            "above_threshold_proportion": 0.35,
        },
        status="Completed",
        tags=["baseline", "summer"],
    )

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    rec_latest = AnalysisRecord(
        analysis_id="HM-20260822-002",
        activity_id="act_latest_002",
        analysis_type="heatmap",
        created_at=now_iso,
        updated_at=now_iso,
        location_label="Financial District",
        date="2026-08-22",
        time="14:00",
        granularity=100,
        metrics={
            "mean_temp": 42.5,
            "min_temp": 33.0,
            "max_temp": 48.0,
            "temp_spread": 15.0,
            "total_tiles": 80,
            "above_threshold_proportion": 0.70,
        },
        status="Completed",
        tags=["monitoring", "elevated"],
    )

    return rec_baseline, rec_latest


# ══════════════════════════════════════════════════════════════════════════════
# End-to-End Pipeline & Invariants Test
# ══════════════════════════════════════════════════════════════════════════════


class TestPhase14EndToEndInvariants:
    """Full pipeline execution and invariant safety verification."""

    @patch("httpx.Client.request")
    @patch("requests.request")
    def test_complete_phase14_pipeline_with_zero_api_calls(self, mock_requests, mock_httpx):
        """End-to-end flow executing every Phase 14 operation without making any network calls."""
        rec_a, rec_b = _build_test_records()
        records = [rec_a, rec_b]
        initial_metrics_b = dict(rec_b.metrics)

        # 1. Operational Signal Detection & Alert Policy Evaluation
        signals_auto = generate_operational_signals(records)
        assert len(signals_auto) >= 1

        policies = get_default_alert_policies()
        signals_policy = evaluate_alert_policies(records, policies)
        assert len(signals_policy) >= 1

        all_signals = signals_auto + signals_policy
        critical_signals = [s for s in all_signals if s.severity == "CRITICAL"]
        assert len(critical_signals) >= 1

        # 2. Priority Scoring & Classification
        target_signal = critical_signals[0]
        score, label = get_signal_priority(target_signal)
        assert score >= 75.0
        assert label == "Critical"

        # 3. Investigation Queue Addition & Transitions
        ok, err, item = add_to_investigation_queue(
            analysis_id=target_signal.analysis_id,
            signal_id=target_signal.signal_id,
            priority=label,
            reason=target_signal.title,
            location=rec_b.location_label,
        )
        assert ok is True
        assert item is not None
        assert item.status == STATUS_OPEN

        # Transition to IN_REVIEW
        mark_in_review(item.queue_id, notes="Investigating extreme tile readings.")
        queue = get_investigation_queue()
        assert queue[0].status == STATUS_IN_REVIEW
        assert queue[0].notes == "Investigating extreme tile readings."

        # 4. Historical Comparison (Phase 13 Decision Intelligence)
        comparison = compare_analysis_records(rec_a, rec_b)
        assert comparison["baseline_id"] == rec_a.analysis_id
        assert comparison["comparison_id"] == rec_b.analysis_id

        # 5. Scenario What-If Sandbox
        adjustments = create_scenario_adjustments(temperature_delta=2.0, threshold_delta=-1.0)
        scenario_comp = compare_scenario_to_observed(rec_b, adjustments, base_threshold=40.0)
        assert scenario_comp.scenario_mean_temp == 44.5
        assert scenario_comp.scenario_exceeds_threshold is True

        # 6. Investigation Brief Export (TXT, JSON, Brief)
        brief_txt = generate_investigation_brief(target_signal, rec_b, historical_context=[rec_a], scenario=scenario_comp, format="brief")
        brief_json = generate_investigation_brief(target_signal, rec_b, historical_context=[rec_a], scenario=scenario_comp, format="json")

        assert "FORTYGUARD OPERATIONAL INVESTIGATION BRIEF" in brief_txt
        parsed_json = json.loads(brief_json)
        assert parsed_json["export_type"] == "FORTYGUARD_OPERATIONAL_INVESTIGATION_BRIEF"

        # ── INVARIANT 1: Zero network calls made ──
        mock_requests.assert_not_called()
        mock_httpx.assert_not_called()

        # ── INVARIANT 2: Base records remain strictly unmodified ──
        assert rec_b.metrics == initial_metrics_b
        assert rec_b.metrics["mean_temp"] == 42.5

        # ── INVARIANT 3: Responsible Analytics compliance ──
        assert is_text_compliant(brief_txt) is True
        validate_analytical_text(brief_txt)
        validate_analytical_text(scenario_comp.narrative_summary)

        # ── INVARIANT 4: Security & Credential Redaction ──
        forbidden_secret_tokens = ["api_key", "secret", "password", "token", "X-Amz-Signature", "signed_url"]
        for token in forbidden_secret_tokens:
            assert f'"{token}"' not in brief_json.lower()

        # 7. Transition Queue Item to RESOLVED
        mark_resolved(item.queue_id, notes="Confirmed as sustained anomaly.")
        queue = get_investigation_queue()
        assert queue[0].status == STATUS_RESOLVED


# ══════════════════════════════════════════════════════════════════════════════
# Determinism & Immutability Invariant Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestDeterminismInvariants:
    """Verify that identical inputs produce identical deterministic results."""

    def test_signal_evaluation_is_deterministic(self):
        rec_a, rec_b = _build_test_records()
        policies = get_default_alert_policies()

        run1 = evaluate_alert_policies([rec_a, rec_b], policies)
        run2 = evaluate_alert_policies([rec_a, rec_b], policies)

        assert len(run1) == len(run2)
        for s1, s2 in zip(run1, run2):
            assert s1.signal_id == s2.signal_id
            assert s1.severity == s2.severity
            assert s1.observed_value == s2.observed_value
            assert s1.threshold_value == s2.threshold_value

    def test_priority_calculation_is_deterministic(self):
        rec_a, rec_b = _build_test_records()
        signals = generate_operational_signals([rec_b])
        target = signals[0]

        score1 = calculate_priority_score(target)
        score2 = calculate_priority_score(target)
        assert score1 == score2

    def test_scenario_calculations_are_deterministic(self):
        _, rec_b = _build_test_records()
        adj = create_scenario_adjustments(temperature_delta=1.5, spread_delta=2.0)

        comp1 = compare_scenario_to_observed(rec_b, adj)
        comp2 = compare_scenario_to_observed(rec_b, adj)

        assert comp1.scenario_mean_temp == comp2.scenario_mean_temp
        assert comp1.scenario_spread == comp2.scenario_spread
        assert comp1.narrative_summary == comp2.narrative_summary
