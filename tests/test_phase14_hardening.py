"""Phase 14 production hardening tests — lifecycle, explainability, compatibility, network."""

from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

from frontend.utils.alert_engine import (
    LIFECYCLE_ACKNOWLEDGED,
    LIFECYCLE_DISMISSED,
    LIFECYCLE_INVESTIGATING,
    LIFECYCLE_NEW,
    LIFECYCLE_RESOLVED,
    can_transition_lifecycle,
    get_signal_lifecycle_status,
    resolve_signal,
    start_investigating_signal,
    transition_signal_lifecycle,
)
from frontend.utils.analysis_history import AnalysisRecord
from frontend.utils.operational_intelligence import generate_operational_signals
from frontend.utils.priority import calculate_priority_score, explain_priority_score
from frontend.utils.responsible_analytics import (
    ResponsibleAnalyticsViolation,
    check_prohibited_terms,
    sanitize_narrative_text,
    validate_analytical_text,
)
from frontend.utils.scenario_engine import (
    SCENARIO_ANALYTICS_DISCLAIMER,
    compare_scenario_to_observed,
    create_scenario_adjustments,
)


@pytest.fixture(autouse=True)
def _clear_streamlit_session(monkeypatch):
    import streamlit as st

    st.session_state.clear()
    yield
    st.session_state.clear()


def _sample_record(**overrides) -> AnalysisRecord:
    base = dict(
        analysis_id="HM-HARDEN-001",
        activity_id="act-harden-1",
        analysis_type="heatmap",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Harbor District",
        date="2026-08-22",
        time="14:00",
        granularity=100,
        metrics={
            "mean_temp": 41.0,
            "min_temp": 33.0,
            "max_temp": 48.0,
            "temp_spread": 15.0,
            "total_tiles": 80,
            "above_threshold_proportion": 0.4,
        },
        status="Completed",
    )
    base.update(overrides)
    return AnalysisRecord(**base)


class TestLifecycleTransitions:
    def test_valid_path_new_to_resolved(self):
        assert can_transition_lifecycle(LIFECYCLE_NEW, LIFECYCLE_ACKNOWLEDGED)
        ok, err = transition_signal_lifecycle("SIG-1", LIFECYCLE_ACKNOWLEDGED)
        assert ok and err is None
        assert get_signal_lifecycle_status("SIG-1") == LIFECYCLE_ACKNOWLEDGED

        ok, err = start_investigating_signal("SIG-1")
        assert ok and err is None
        assert get_signal_lifecycle_status("SIG-1") == LIFECYCLE_INVESTIGATING

        ok, err = resolve_signal("SIG-1")
        assert ok and err is None
        assert get_signal_lifecycle_status("SIG-1") == LIFECYCLE_RESOLVED

    def test_illegal_transition_rejected(self):
        ok, err = transition_signal_lifecycle("SIG-2", LIFECYCLE_RESOLVED, enforce=True)
        assert not ok
        assert err is not None
        assert get_signal_lifecycle_status("SIG-2") == LIFECYCLE_NEW

    def test_dismiss_from_new_allowed(self):
        assert can_transition_lifecycle(LIFECYCLE_NEW, LIFECYCLE_DISMISSED)
        ok, err = transition_signal_lifecycle("SIG-3", LIFECYCLE_DISMISSED)
        assert ok and err is None


class TestPriorityExplainability:
    def test_explanation_matches_score(self):
        rec = _sample_record()
        signals = generate_operational_signals([rec])
        assert signals
        target = signals[0]
        score = calculate_priority_score(target)
        explained = explain_priority_score(target)
        assert explained["score"] == score
        assert "explanation" in explained
        assert explained["factors"]["severity"] == target.severity.upper()

    def test_explanation_handles_missing_magnitude_inputs(self):
        explained = explain_priority_score(
            {
                "signal_id": "SIG-X",
                "severity": "WATCH",
                "signal_type": "data_quality",
                "observed_value": None,
                "threshold_value": None,
                "created_at": "2026-08-22T10:00:00",
                "data_quality": "LOW",
            }
        )
        assert explained["score"] >= 0
        assert "missing" in explained["factors"]["magnitude_note"].lower()


class TestImmutabilityAndScenario:
    def test_scenario_does_not_mutate_record(self):
        rec = _sample_record()
        before = copy.deepcopy(rec.to_dict())
        adj = create_scenario_adjustments(temperature_delta=2.5)
        comparison = compare_scenario_to_observed(rec, adj)
        after = rec.to_dict()
        assert before == after
        assert "hypothetical" in comparison.narrative_summary.lower() or "adjustment" in comparison.narrative_summary.lower()
        assert "do not constitute" in SCENARIO_ANALYTICS_DISCLAIMER.lower() or "not" in SCENARIO_ANALYTICS_DISCLAIMER.lower()


class TestResponsibleAnalytics:
    def test_forbidden_causal_terms_detected(self):
        hits = check_prohibited_terms("Warming caused by traffic congestion")
        assert hits

    def test_enforce_raises_on_medical_claim(self):
        with pytest.raises(ResponsibleAnalyticsViolation):
            validate_analytical_text("This presents a health risk to workers", "test")

    def test_sanitize_replaces_forbidden_phrases(self):
        cleaned = sanitize_narrative_text("Increase due to urban density")
        assert "due to" not in cleaned.lower()


class TestZeroNetworkPhase14:
    def test_signal_generation_makes_zero_http_calls(self):
        rec = _sample_record()
        with patch("httpx.Client") as mock_client, patch("httpx.request") as mock_req:
            signals = generate_operational_signals([rec])
            assert isinstance(signals, list)
            mock_client.assert_not_called()
            mock_req.assert_not_called()

    def test_scenario_makes_zero_http_calls(self):
        rec = _sample_record()
        adj = create_scenario_adjustments(temperature_delta=1.0)
        with patch("httpx.Client") as mock_client:
            compare_scenario_to_observed(rec, adj)
            mock_client.assert_not_called()
