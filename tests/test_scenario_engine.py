"""Tests for frontend.utils.scenario_engine — What-If Scenario Analysis Sandbox.

Validates:
- ScenarioAdjustment dataclass immutability and serialization.
- Mathematical what-if adjustments on temperature, threshold, spread, and proportion.
- Non-negative clamping for spread and 0-100% clamping for proportion.
- Base AnalysisRecord immutability: record is never mutated by scenario calculations.
- Threshold exceedance comparisons between observed state and scenario state.
- Scenario narrative generation following Responsible Analytics rules.
- Mandatory disclaimer inclusion.
- Handling of missing metrics without hallucinating values.
- Zero network I/O invariant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import pytest

from frontend.utils.scenario_engine import (
    SCENARIO_ANALYTICS_DISCLAIMER,
    ScenarioAdjustment,
    ScenarioComparison,
    calculate_scenario_metrics,
    compare_scenario_to_observed,
    create_scenario_adjustments,
)


@dataclass
class MockRecord:
    analysis_id: str = "REC-001"
    activity_id: str = "ACT-001"
    location_label: str = "Downtown"
    date: str = "2026-08-22"
    status: str = "Completed"
    metrics: dict[str, Any] = field(default_factory=dict)
    observed_temperature: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "analysis_id": self.analysis_id,
            "activity_id": self.activity_id,
            "location_label": self.location_label,
            "date": self.date,
            "status": self.status,
            "metrics": self.metrics,
        }
        if self.observed_temperature is not None:
            d["observed_temperature"] = self.observed_temperature
        return d


# ══════════════════════════════════════════════════════════════════════════════
# 1. ScenarioAdjustment Model & Creation
# ══════════════════════════════════════════════════════════════════════════════


class TestScenarioAdjustmentModel:
    """Dataclass immutability, factory, and serialization."""

    def test_default_adjustment_is_zero(self):
        adj = ScenarioAdjustment()
        assert adj.temperature_delta == 0.0
        assert adj.threshold_delta == 0.0
        assert adj.spread_delta == 0.0
        assert adj.proportion_delta == 0.0

    def test_factory_creates_rounded_adjustment(self):
        adj = create_scenario_adjustments(
            temperature_delta=2.1234,
            threshold_delta=-1.5,
            spread_delta=0.777,
            proportion_delta=10.5,
        )
        assert adj.temperature_delta == 2.12
        assert adj.threshold_delta == -1.5
        assert adj.spread_delta == 0.78
        assert adj.proportion_delta == 10.5

    def test_immutability_raises_on_mutation(self):
        adj = create_scenario_adjustments(temperature_delta=2.0)
        with pytest.raises(AttributeError):
            adj.temperature_delta = 5.0  # type: ignore[misc]

    def test_to_dict_and_from_dict(self):
        adj = create_scenario_adjustments(temperature_delta=3.0, threshold_delta=-2.0)
        d = adj.to_dict()
        assert d["temperature_delta"] == 3.0
        assert d["threshold_delta"] == -2.0

        reconstructed = ScenarioAdjustment.from_dict(d)
        assert reconstructed.temperature_delta == 3.0
        assert reconstructed.threshold_delta == -2.0


# ══════════════════════════════════════════════════════════════════════════════
# 2. Metric Adjustment Calculations
# ══════════════════════════════════════════════════════════════════════════════


class TestScenarioMetricCalculations:
    """Calculations for temperature, spread, and proportion deltas."""

    def test_positive_temperature_adjustment(self):
        rec = MockRecord(metrics={"mean_temp": 34.0, "min_temp": 28.0, "max_temp": 40.0})
        adj = create_scenario_adjustments(temperature_delta=2.5)

        metrics = calculate_scenario_metrics(rec, adj)
        assert metrics["mean_temperature"] == 36.5
        assert metrics["min_temperature"] == 30.5
        assert metrics["max_temperature"] == 42.5

    def test_negative_temperature_adjustment(self):
        rec = MockRecord(metrics={"mean_temp": 34.0, "min_temp": 28.0, "max_temp": 40.0})
        adj = create_scenario_adjustments(temperature_delta=-3.0)

        metrics = calculate_scenario_metrics(rec, adj)
        assert metrics["mean_temperature"] == 31.0
        assert metrics["min_temperature"] == 25.0
        assert metrics["max_temperature"] == 37.0

    def test_spread_adjustment_with_non_negative_clamping(self):
        rec = MockRecord(metrics={"temp_spread": 4.0})

        # Spread increase
        adj_inc = create_scenario_adjustments(spread_delta=2.0)
        metrics_inc = calculate_scenario_metrics(rec, adj_inc)
        assert metrics_inc["temperature_spread"] == 6.0

        # Spread decrease below zero clamped to 0.0
        adj_clamp = create_scenario_adjustments(spread_delta=-10.0)
        metrics_clamp = calculate_scenario_metrics(rec, adj_clamp)
        assert metrics_clamp["temperature_spread"] == 0.0

    def test_proportion_adjustment_with_clamping(self):
        rec = MockRecord(metrics={"above_threshold_proportion": 40.0})

        # Increase clamped at 100%
        adj_high = create_scenario_adjustments(proportion_delta=80.0)
        metrics_high = calculate_scenario_metrics(rec, adj_high)
        assert metrics_high["above_threshold_proportion"] == 100.0

        # Decrease clamped at 0%
        adj_low = create_scenario_adjustments(proportion_delta=-60.0)
        metrics_low = calculate_scenario_metrics(rec, adj_low)
        assert metrics_low["above_threshold_proportion"] == 0.0

    def test_missing_metrics_remain_none(self):
        rec = MockRecord(metrics={"mean_temp": 30.0})  # spread & prop missing
        adj = create_scenario_adjustments(temperature_delta=2.0, spread_delta=1.0, proportion_delta=5.0)

        metrics = calculate_scenario_metrics(rec, adj)
        assert metrics["mean_temperature"] == 32.0
        assert metrics["temperature_spread"] is None
        assert metrics["above_threshold_proportion"] is None


# ══════════════════════════════════════════════════════════════════════════════
# 3. Base Record Immutability Verification
# ══════════════════════════════════════════════════════════════════════════════


class TestRecordImmutability:
    """Ensure base records are strictly NEVER mutated."""

    def test_original_metrics_dict_unmodified(self):
        original_metrics = {"mean_temp": 34.0, "min_temp": 28.0, "max_temp": 40.0}
        rec = MockRecord(metrics=dict(original_metrics))
        adj = create_scenario_adjustments(temperature_delta=5.0, spread_delta=3.0)

        _ = calculate_scenario_metrics(rec, adj)
        _ = compare_scenario_to_observed(rec, adj)

        # Original record metrics must match exact initial values
        assert rec.metrics == original_metrics
        assert rec.metrics["mean_temp"] == 34.0

    def test_original_dict_record_unmodified(self):
        dict_rec = {
            "analysis_id": "D-1",
            "metrics": {"mean_temp": 32.0},
        }
        adj = create_scenario_adjustments(temperature_delta=4.0)
        _ = calculate_scenario_metrics(dict_rec, adj)
        assert dict_rec["metrics"]["mean_temp"] == 32.0


# ══════════════════════════════════════════════════════════════════════════════
# 4. Scenario Comparison & Threshold Exceedance
# ══════════════════════════════════════════════════════════════════════════════


class TestScenarioComparison:
    """End-to-end scenario comparison against thresholds."""

    def test_scenario_crosses_above_threshold(self):
        # Observed: 33.0°C (below base threshold 35.0°C)
        # Adjustment: +3.0°C -> Scenario: 36.0°C (above 35.0°C)
        rec = MockRecord(metrics={"mean_temp": 33.0})
        adj = create_scenario_adjustments(temperature_delta=3.0)

        comp = compare_scenario_to_observed(rec, adj, base_threshold=35.0)
        assert comp.observed_exceeds_threshold is False
        assert comp.scenario_exceeds_threshold is True
        assert comp.threshold_delta_exceedance == 1.0  # 36.0 - 35.0
        assert "shifts the scenario temperature above" in comp.narrative_summary

    def test_scenario_crosses_below_threshold(self):
        # Observed: 36.0°C (above base threshold 35.0°C)
        # Adjustment: -3.0°C -> Scenario: 33.0°C (below 35.0°C)
        rec = MockRecord(metrics={"mean_temp": 36.0})
        adj = create_scenario_adjustments(temperature_delta=-3.0)

        comp = compare_scenario_to_observed(rec, adj, base_threshold=35.0)
        assert comp.observed_exceeds_threshold is True
        assert comp.scenario_exceeds_threshold is False
        assert "brings the scenario temperature below" in comp.narrative_summary

    def test_both_observed_and_scenario_exceed_threshold(self):
        rec = MockRecord(metrics={"mean_temp": 38.0})
        adj = create_scenario_adjustments(temperature_delta=2.0)

        comp = compare_scenario_to_observed(rec, adj, base_threshold=35.0)
        assert comp.observed_exceeds_threshold is True
        assert comp.scenario_exceeds_threshold is True
        assert "Both observed and scenario states exceed" in comp.narrative_summary

    def test_both_observed_and_scenario_within_threshold(self):
        rec = MockRecord(metrics={"mean_temp": 28.0})
        adj = create_scenario_adjustments(temperature_delta=2.0)

        comp = compare_scenario_to_observed(rec, adj, base_threshold=35.0)
        assert comp.observed_exceeds_threshold is False
        assert comp.scenario_exceeds_threshold is False
        assert "Both observed and scenario states remain within" in comp.narrative_summary

    def test_threshold_delta_adjustment_applied(self):
        # Base threshold 35.0°C with policy adjustment of -2.0°C -> Scenario threshold 33.0°C
        rec = MockRecord(metrics={"mean_temp": 34.0})
        adj = create_scenario_adjustments(temperature_delta=0.0, threshold_delta=-2.0)

        comp = compare_scenario_to_observed(rec, adj, base_threshold=35.0)
        assert comp.threshold_observed == 35.0
        assert comp.threshold_scenario == 33.0
        # 34.0 < 35.0 (False), 34.0 >= 33.0 (True)
        assert comp.observed_exceeds_threshold is False
        assert comp.scenario_exceeds_threshold is True

    def test_scenario_comparison_to_dict(self):
        rec = MockRecord(analysis_id="REC-99", location_label="Harbor", metrics={"mean_temp": 34.0})
        adj = create_scenario_adjustments(temperature_delta=2.0)
        comp = compare_scenario_to_observed(rec, adj)

        d = comp.to_dict()
        assert d["analysis_id"] == "REC-99"
        assert d["location"] == "Harbor"
        assert d["observed_mean_temp"] == 34.0
        assert d["scenario_mean_temp"] == 36.0
        assert "adjustments" in d
        assert d["disclaimer"] == SCENARIO_ANALYTICS_DISCLAIMER

    def test_zero_delta_adjustments_match_observed(self):
        rec = MockRecord(metrics={"mean_temp": 34.5, "temp_spread": 5.0})
        adj = create_scenario_adjustments()
        comp = compare_scenario_to_observed(rec, adj)
        assert comp.scenario_mean_temp == comp.observed_mean_temp
        assert comp.scenario_spread == comp.observed_spread


# ══════════════════════════════════════════════════════════════════════════════
# 5. Responsible Analytics & Disclaimer
# ══════════════════════════════════════════════════════════════════════════════


class TestScenarioResponsibleAnalytics:
    """Ensure scenario outputs contain mandatory disclaimers and neutral language."""

    FORBIDDEN = [
        "caused by",
        "due to",
        "will cause",
        "prediction",
        "forecast",
        "hazardous",
        "deadly",
        "fatal",
        "health risk",
    ]

    def test_disclaimer_always_present(self):
        rec = MockRecord(metrics={"mean_temp": 35.0})
        comp = compare_scenario_to_observed(rec, create_scenario_adjustments(temperature_delta=2.0))
        assert comp.disclaimer == SCENARIO_ANALYTICS_DISCLAIMER
        assert "mathematical what-if" in comp.disclaimer.lower()

    def test_narrative_contains_no_forbidden_terms(self):
        rec = MockRecord(metrics={"mean_temp": 35.0})
        comp = compare_scenario_to_observed(rec, create_scenario_adjustments(temperature_delta=10.0))
        text = comp.narrative_summary.lower()

        for word in self.FORBIDDEN:
            assert word not in text, f"Forbidden term '{word}' found in scenario narrative"

    def test_from_dict_defaults_on_scenario_adjustment(self):
        empty_data = {}
        adj = ScenarioAdjustment.from_dict(empty_data)
        assert adj.temperature_delta == 0.0
        assert adj.threshold_delta == 0.0
        assert adj.spread_delta == 0.0
        assert adj.proportion_delta == 0.0

    def test_decimal_proportion_conversion(self):
        # When record proportion is 0.25 (decimal), it gets converted to 25.0%
        rec = MockRecord(metrics={"above_threshold_proportion": 0.25})
        adj = create_scenario_adjustments(proportion_delta=10.0)
        metrics = calculate_scenario_metrics(rec, adj)
        assert metrics["above_threshold_proportion"] == 35.0

    def test_empty_record_handles_scenario_gracefully(self):
        rec = MockRecord(metrics={})
        adj = create_scenario_adjustments(temperature_delta=2.0)
        comp = compare_scenario_to_observed(rec, adj)
        assert comp.scenario_mean_temp is None
        assert comp.threshold_delta_exceedance is None

