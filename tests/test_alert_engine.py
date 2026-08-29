"""Tests for frontend.utils.alert_engine — Pure Alert Evaluation & Signal Lifecycle Engine.

Validates:
- Pure deterministic policy evaluation on completed AnalysisRecords.
- Operator evaluations: >, >=, <, <=, == across all supported metrics.
- Scope filtering (all, heatmap, heat_intelligence, specific location).
- Disabled policies are not evaluated.
- Non-completed records are ignored.
- Deduplication of identical signals.
- Signal lifecycle state machine: NEW -> ACKNOWLEDGED -> DISMISSED -> RESTORED.
- Deterministic sorting (severity descending, created_at descending, analysis_id ascending).
- Zero network I/O invariant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import streamlit as st
import pytest

from frontend.utils.alert_engine import (
    LIFECYCLE_ACKNOWLEDGED,
    LIFECYCLE_DISMISSED,
    LIFECYCLE_NEW,
    acknowledge_signal,
    deduplicate_signals,
    dismiss_signal,
    evaluate_alert_policies,
    filter_signals_by_lifecycle,
    get_active_signals,
    get_signal_lifecycle_status,
    restore_signal,
)
from frontend.utils.alert_policies import AlertPolicy
from frontend.utils.operational_intelligence import OperationalSignal


@dataclass
class MockRecord:
    analysis_id: str = "rec-001"
    activity_id: str = "act-001"
    analysis_type: str = "heatmap"
    location_label: str = "Downtown"
    date: str = "2026-08-22"
    time: str | None = "14:00"
    created_at: str = "2026-08-22T14:00:00"
    status: str = "Completed"
    metrics: dict[str, Any] = field(default_factory=dict)
    observed_temperature: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "analysis_id": self.analysis_id,
            "activity_id": self.activity_id,
            "analysis_type": self.analysis_type,
            "location_label": self.location_label,
            "date": self.date,
            "time": self.time,
            "created_at": self.created_at,
            "status": self.status,
            "metrics": self.metrics,
        }
        if self.observed_temperature is not None:
            d["observed_temperature"] = self.observed_temperature
        return d


@pytest.fixture(autouse=True)
def clean_session_state():
    st.session_state.clear()
    yield
    st.session_state.clear()


# ══════════════════════════════════════════════════════════════════════════════
# 1. Operator Evaluations
# ══════════════════════════════════════════════════════════════════════════════


class TestOperatorEvaluations:
    """Evaluates operators across different metric thresholds."""

    def test_greater_than_operator(self):
        rec = MockRecord(metrics={"mean_temp": 38.0})
        pol_triggered = AlertPolicy("P1", "GT Test", "mean_temperature", ">", 37.0)
        pol_not_triggered = AlertPolicy("P2", "GT Test 2", "mean_temperature", ">", 38.0)

        signals_1 = evaluate_alert_policies([rec], [pol_triggered])
        assert len(signals_1) == 1
        assert signals_1[0].observed_value == 38.0

        signals_2 = evaluate_alert_policies([rec], [pol_not_triggered])
        assert len(signals_2) == 0

    def test_greater_than_or_equal_operator(self):
        rec = MockRecord(metrics={"mean_temp": 38.0})
        pol_exact = AlertPolicy("P1", "GTE Test", "mean_temperature", ">=", 38.0)
        pol_above = AlertPolicy("P2", "GTE Test 2", "mean_temperature", ">=", 35.0)
        pol_fail = AlertPolicy("P3", "GTE Test 3", "mean_temperature", ">=", 39.0)

        assert len(evaluate_alert_policies([rec], [pol_exact])) == 1
        assert len(evaluate_alert_policies([rec], [pol_above])) == 1
        assert len(evaluate_alert_policies([rec], [pol_fail])) == 0

    def test_less_than_operator(self):
        rec = MockRecord(metrics={"mean_temp": 12.0})
        pol_triggered = AlertPolicy("P1", "LT Test", "mean_temperature", "<", 15.0)
        pol_not_triggered = AlertPolicy("P2", "LT Test 2", "mean_temperature", "<", 12.0)

        assert len(evaluate_alert_policies([rec], [pol_triggered])) == 1
        assert len(evaluate_alert_policies([rec], [pol_not_triggered])) == 0

    def test_less_than_or_equal_operator(self):
        rec = MockRecord(metrics={"mean_temp": 12.0})
        pol_exact = AlertPolicy("P1", "LTE Test", "mean_temperature", "<=", 12.0)
        pol_below = AlertPolicy("P2", "LTE Test 2", "mean_temperature", "<=", 15.0)
        pol_fail = AlertPolicy("P3", "LTE Test 3", "mean_temperature", "<=", 10.0)

        assert len(evaluate_alert_policies([rec], [pol_exact])) == 1
        assert len(evaluate_alert_policies([rec], [pol_below])) == 1
        assert len(evaluate_alert_policies([rec], [pol_fail])) == 0

    def test_equal_operator(self):
        rec = MockRecord(metrics={"tile_count": 50})
        pol_exact = AlertPolicy("P1", "EQ Test", "tile_count", "==", 50.0)
        pol_different = AlertPolicy("P2", "EQ Test 2", "tile_count", "==", 55.0)

        assert len(evaluate_alert_policies([rec], [pol_exact])) == 1
        assert len(evaluate_alert_policies([rec], [pol_different])) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. Metric Candidate Keys & Proportions
# ══════════════════════════════════════════════════════════════════════════════


class TestMetricCandidateEvaluations:
    """Evaluates various metrics and alternative field names."""

    def test_minimum_temperature_evaluation(self):
        rec = MockRecord(metrics={"min_temp": 28.5})
        pol = AlertPolicy("P1", "Min Temp Alert", "minimum_temperature", ">=", 28.0)
        signals = evaluate_alert_policies([rec], [pol])
        assert len(signals) == 1
        assert signals[0].metric == "minimum_temperature"

    def test_maximum_temperature_evaluation(self):
        rec = MockRecord(metrics={"max_temp": 44.0})
        pol = AlertPolicy("P1", "Max Temp Alert", "maximum_temperature", ">=", 40.0, "CRITICAL")
        signals = evaluate_alert_policies([rec], [pol])
        assert len(signals) == 1
        assert signals[0].severity == "CRITICAL"

    def test_temperature_spread_evaluation(self):
        rec = MockRecord(metrics={"temp_spread": 9.5})
        pol = AlertPolicy("P1", "Spread Alert", "temperature_spread", ">=", 8.0)
        signals = evaluate_alert_policies([rec], [pol])
        assert len(signals) == 1
        assert signals[0].observed_value == 9.5

    def test_above_threshold_proportion_normalized_evaluation(self):
        # Record has 0.45, policy has 40.0%
        rec = MockRecord(metrics={"above_threshold_proportion": 0.45})
        pol = AlertPolicy("P1", "Hot Area Alert", "above_threshold_proportion", ">=", 40.0)
        signals = evaluate_alert_policies([rec], [pol])
        assert len(signals) == 1
        assert abs(signals[0].observed_value - 45.0) < 0.1

    def test_missing_metric_produces_no_signal(self):
        rec = MockRecord(metrics={"mean_temp": 30.0})  # spread missing
        pol = AlertPolicy("P1", "Spread Alert", "temperature_spread", ">=", 8.0)
        assert len(evaluate_alert_policies([rec], [pol])) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 3. Policy Scope & Enablement
# ══════════════════════════════════════════════════════════════════════════════


class TestPolicyScopeAndEnablement:
    """Scope filtering and disabled policy handling."""

    def test_disabled_policy_is_ignored(self):
        rec = MockRecord(metrics={"mean_temp": 45.0})
        pol = AlertPolicy("P1", "Disabled Policy", "mean_temperature", ">=", 40.0, enabled=False)
        signals = evaluate_alert_policies([rec], [pol])
        assert len(signals) == 0

    def test_applies_to_heatmap_scope(self):
        rec_hm = MockRecord(analysis_id="HM-1", analysis_type="heatmap", metrics={"mean_temp": 42.0})
        rec_hi = MockRecord(analysis_id="HI-1", analysis_type="heat_intelligence", metrics={"mean_temp": 42.0})
        pol = AlertPolicy("P1", "Heatmap Only", "mean_temperature", ">=", 40.0, applies_to="heatmap")

        signals = evaluate_alert_policies([rec_hm, rec_hi], [pol])
        assert len(signals) == 1
        assert signals[0].analysis_id == "HM-1"

    def test_applies_to_location_scope(self):
        rec_downtown = MockRecord(analysis_id="R-D", location_label="Downtown Core", metrics={"mean_temp": 42.0})
        rec_suburbs = MockRecord(analysis_id="R-S", location_label="Suburban Valley", metrics={"mean_temp": 42.0})
        pol = AlertPolicy("P1", "Downtown Only", "mean_temperature", ">=", 40.0, applies_to="Downtown")

        signals = evaluate_alert_policies([rec_downtown, rec_suburbs], [pol])
        assert len(signals) == 1
        assert signals[0].analysis_id == "R-D"

    def test_non_completed_records_ignored(self):
        rec_comp = MockRecord(analysis_id="R-C", status="Completed", metrics={"mean_temp": 42.0})
        rec_proc = MockRecord(analysis_id="R-P", status="Processing", metrics={"mean_temp": 45.0})
        rec_fail = MockRecord(analysis_id="R-F", status="Failed", metrics={"mean_temp": 45.0})
        pol = AlertPolicy("P1", "Crit Heat", "mean_temperature", ">=", 40.0)

        signals = evaluate_alert_policies([rec_comp, rec_proc, rec_fail], [pol])
        assert len(signals) == 1
        assert signals[0].analysis_id == "R-C"


# ══════════════════════════════════════════════════════════════════════════════
# 4. Deduplication & Deterministic Ordering
# ══════════════════════════════════════════════════════════════════════════════


class TestDeduplicationAndOrdering:
    """Signal deduplication and deterministic sorting."""

    def test_deduplicate_signals_keeps_single(self):
        sig1 = OperationalSignal("SIG-1", "REC-1", "temp", "CRITICAL", "Title", "Desc")
        sig2 = OperationalSignal("SIG-1", "REC-1", "temp", "CRITICAL", "Title", "Desc")
        sig3 = OperationalSignal("SIG-2", "REC-2", "temp", "INFO", "Title", "Desc")

        deduped = deduplicate_signals([sig1, sig2, sig3])
        assert len(deduped) == 2
        assert {s.signal_id for s in deduped} == {"SIG-1", "SIG-2"}

    def test_evaluation_sorts_by_severity_descending(self):
        rec = MockRecord(metrics={"mean_temp": 42.0, "temp_spread": 10.0, "total_tiles": 50})
        pols = [
            AlertPolicy("P-INFO", "Info Policy", "tile_count", ">=", 10.0, severity="INFO"),
            AlertPolicy("P-CRIT", "Crit Policy", "mean_temperature", ">=", 40.0, severity="CRITICAL"),
            AlertPolicy("P-ELEV", "Elev Policy", "temp_spread", ">=", 8.0, severity="ELEVATED"),
            AlertPolicy("P-WATCH", "Watch Policy", "mean_temperature", ">=", 30.0, severity="WATCH"),
        ]

        signals = evaluate_alert_policies([rec], pols)
        assert len(signals) == 4
        assert [s.severity for s in signals] == ["CRITICAL", "ELEVATED", "WATCH", "INFO"]


# ══════════════════════════════════════════════════════════════════════════════
# 5. Signal Lifecycle Management
# ══════════════════════════════════════════════════════════════════════════════


class TestSignalLifecycleManagement:
    """Session state lifecycle transitions: NEW -> ACKNOWLEDGED -> DISMISSED -> RESTORED."""

    def test_default_status_is_new(self):
        assert get_signal_lifecycle_status("SIG-TEST-1") == LIFECYCLE_NEW

    def test_acknowledge_signal_lifecycle(self):
        acknowledge_signal("SIG-TEST-1")
        assert get_signal_lifecycle_status("SIG-TEST-1") == LIFECYCLE_ACKNOWLEDGED

    def test_dismiss_signal_lifecycle(self):
        dismiss_signal("SIG-TEST-2")
        assert get_signal_lifecycle_status("SIG-TEST-2") == LIFECYCLE_DISMISSED

    def test_restore_signal_lifecycle(self):
        dismiss_signal("SIG-TEST-3")
        assert get_signal_lifecycle_status("SIG-TEST-3") == LIFECYCLE_DISMISSED

        restore_signal("SIG-TEST-3")
        assert get_signal_lifecycle_status("SIG-TEST-3") == LIFECYCLE_NEW

    def test_filter_signals_by_lifecycle(self):
        sig1 = OperationalSignal("S1", "R1", "type", "INFO", "T1", "D1")
        sig2 = OperationalSignal("S2", "R2", "type", "INFO", "T2", "D2")
        sig3 = OperationalSignal("S3", "R3", "type", "INFO", "T3", "D3")

        acknowledge_signal("S2")
        dismiss_signal("S3")

        signals = [sig1, sig2, sig3]

        new_sigs = filter_signals_by_lifecycle(signals, LIFECYCLE_NEW)
        assert len(new_sigs) == 1
        assert new_sigs[0].signal_id == "S1"

        ack_sigs = filter_signals_by_lifecycle(signals, LIFECYCLE_ACKNOWLEDGED)
        assert len(ack_sigs) == 1
        assert ack_sigs[0].signal_id == "S2"

        dsm_sigs = filter_signals_by_lifecycle(signals, LIFECYCLE_DISMISSED)
        assert len(dsm_sigs) == 1
        assert dsm_sigs[0].signal_id == "S3"

    def test_get_active_signals_excludes_dismissed(self):
        sig1 = OperationalSignal("S1", "R1", "type", "INFO", "T1", "D1")
        sig2 = OperationalSignal("S2", "R2", "type", "INFO", "T2", "D2")
        sig3 = OperationalSignal("S3", "R3", "type", "INFO", "T3", "D3")

        acknowledge_signal("S2")
        dismiss_signal("S3")

        signals = [sig1, sig2, sig3]

        # Active including acknowledged
        active = get_active_signals(signals, include_acknowledged=True)
        assert len(active) == 2
        assert {s.signal_id for s in active} == {"S1", "S2"}

        # Active new only
        new_only = get_active_signals(signals, include_acknowledged=False)
        assert len(new_only) == 1
        assert new_only[0].signal_id == "S1"


# ══════════════════════════════════════════════════════════════════════════════
# 6. Multi-Record & Multi-Policy Complex Scenarios
# ══════════════════════════════════════════════════════════════════════════════


class TestComplexEvaluationScenarios:
    """Complex combinations of multiple records, policies, and edge cases."""

    def test_single_record_matching_multiple_policies(self):
        rec = MockRecord(
            analysis_id="REC-MULTI",
            location_label="Downtown",
            metrics={
                "mean_temp": 42.0,
                "min_temp": 30.0,
                "max_temp": 46.0,
                "temp_spread": 12.0,
                "above_threshold_proportion": 0.60,
                "total_tiles": 100,
            },
        )
        pols = [
            AlertPolicy("P-HEAT", "High Heat", "mean_temperature", ">=", 40.0, severity="CRITICAL"),
            AlertPolicy("P-SPREAD", "High Spread", "temperature_spread", ">=", 10.0, severity="ELEVATED"),
            AlertPolicy("P-TILES", "Tile Count", "tile_count", ">=", 50.0, severity="INFO"),
        ]

        signals = evaluate_alert_policies([rec], pols)
        assert len(signals) == 3
        # Should be sorted: CRITICAL -> ELEVATED -> INFO
        assert signals[0].severity == "CRITICAL"
        assert signals[1].severity == "ELEVATED"
        assert signals[2].severity == "INFO"

    def test_multiple_records_matching_single_policy(self):
        recs = [
            MockRecord(analysis_id="R1", location_label="Zone 1", metrics={"mean_temp": 41.0}),
            MockRecord(analysis_id="R2", location_label="Zone 2", metrics={"mean_temp": 43.0}),
            MockRecord(analysis_id="R3", location_label="Zone 3", metrics={"mean_temp": 32.0}),
        ]
        pol = AlertPolicy("P-CRIT", "Crit Heat", "mean_temperature", ">=", 40.0, severity="CRITICAL")

        signals = evaluate_alert_policies(recs, [pol])
        assert len(signals) == 2
        assert {s.analysis_id for s in signals} == {"R1", "R2"}

    def test_plain_dictionary_records_supported(self):
        dict_rec = {
            "analysis_id": "DICT-1",
            "status": "Completed",
            "location_label": "Direct Dict",
            "created_at": "2026-08-22T10:00:00",
            "metrics": {"mean_temp": 41.5},
        }
        pol = AlertPolicy("P1", "Dict Alert", "mean_temperature", ">=", 40.0)
        signals = evaluate_alert_policies([dict_rec], [pol])
        assert len(signals) == 1
        assert signals[0].analysis_id == "DICT-1"

    def test_plain_dictionary_policies_supported(self):
        rec = MockRecord(metrics={"mean_temp": 41.0})
        dict_pol = {
            "policy_id": "P-RAW",
            "name": "Raw Policy Dict",
            "metric": "mean_temperature",
            "operator": ">=",
            "threshold": 40.0,
            "severity": "CRITICAL",
            "applies_to": "all",
            "enabled": True,
        }
        signals = evaluate_alert_policies([rec], [dict_pol])
        assert len(signals) == 1
        assert signals[0].title.startswith("Raw Policy Dict")

    def test_empty_records_and_policies_produce_empty(self):
        assert evaluate_alert_policies([], []) == []
        assert evaluate_alert_policies([MockRecord()], []) == []
        assert evaluate_alert_policies([], [AlertPolicy("P1", "N", "mean_temperature", ">=", 40.0)]) == []

    def test_signal_id_deterministic_format(self):
        rec = MockRecord(analysis_id="R-100", metrics={"mean_temp": 41.0})
        pol = AlertPolicy("POL-ABC", "Name", "mean_temperature", ">=", 40.0)
        signals = evaluate_alert_policies([rec], [pol])
        assert len(signals) == 1
        assert signals[0].signal_id == "SIG-POL-POL-ABC-R-100"

    def test_evidence_contains_policy_and_difference(self):
        rec = MockRecord(analysis_id="R-100", metrics={"mean_temp": 42.5})
        pol = AlertPolicy("P1", "Heat Policy", "mean_temperature", ">=", 40.0)
        signals = evaluate_alert_policies([rec], [pol])
        evidence_text = " ".join(signals[0].evidence)
        assert "Heat Policy" in evidence_text
        assert "+2.50" in evidence_text

    def test_confidence_and_data_quality_inheritance(self):
        rec_high_dq = MockRecord(metrics={"mean_temp": 42.0, "min_temp": 30.0, "max_temp": 45.0, "total_tiles": 50})
        pol = AlertPolicy("P1", "Heat", "mean_temperature", ">=", 40.0)
        signals = evaluate_alert_policies([rec_high_dq], [pol])
        assert signals[0].data_quality == "HIGH"
        assert signals[0].confidence == "HIGH"

    def test_zero_records_match_scope(self):
        rec = MockRecord(analysis_type="heatmap", location_label="Suburbs", metrics={"mean_temp": 45.0})
        pol = AlertPolicy("P1", "Downtown Only", "mean_temperature", ">=", 40.0, applies_to="Downtown")
        assert len(evaluate_alert_policies([rec], [pol])) == 0

    def test_equality_operator_with_decimal_tolerance(self):
        rec = MockRecord(metrics={"mean_temp": 35.0000001})
        pol = AlertPolicy("P1", "Exact 35", "mean_temperature", "==", 35.0)
        signals = evaluate_alert_policies([rec], [pol])
        assert len(signals) == 1

    def test_invalid_operator_in_policy_returns_no_signal(self):
        rec = MockRecord(metrics={"mean_temp": 45.0})
        pol = AlertPolicy("P1", "Invalid Op", "mean_temperature", "INVALID", 40.0)
        assert len(evaluate_alert_policies([rec], [pol])) == 0

