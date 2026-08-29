"""Tests for frontend.utils.decision_intelligence — Pure Decision Intelligence Engine.

Validates:
- Pure delta mathematics (including edge cases: None, NaN, Inf, zero baseline).
- Direction classification with tolerance thresholds.
- Metric extraction from nested record structures.
- End-to-end compare_analysis_records with AnalysisRecord instances.
- Data quality indicators (available / missing / comparable ratios).
- Responsible Analytics: no causal language, no medical claims.
- Zero network I/O — all tests are purely deterministic in-memory calculations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pytest

from frontend.utils.decision_intelligence import (
    DECISION_THRESHOLDS,
    RESPONSIBLE_ANALYTICS_DISCLAIMER,
    ComparisonMetric,
    build_comparison_metric,
    calculate_delta,
    classify_direction,
    compare_analysis_records,
)


# ──────────────────────────────────────────────────────────────────────────────
# Shared Fixture: Minimal AnalysisRecord-like objects
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class FakeAnalysisRecord:
    """Minimal stand-in for AnalysisRecord with to_dict support."""

    analysis_id: str = "test-001"
    activity_id: str = "act-001"
    analysis_type: str = "heatmap"
    created_at: str = "2025-06-01T12:00:00"
    updated_at: str = "2025-06-01T12:05:00"
    location_label: str = "Test Location"
    latitude: float | None = 25.0
    longitude: float | None = 55.0
    date: str = "2025-06-01"
    time: str | None = "12:00"
    observed_temperature: float | None = None
    categories: list[str] = field(default_factory=list)
    granularity: int | None = 100
    polygon_summary: str = ""
    polygon_aoi: dict[str, Any] | None = None
    status: str = "Completed"
    summary: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    insights: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    pinned: bool = False
    result_cached: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "activity_id": self.activity_id,
            "analysis_type": self.analysis_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "location_label": self.location_label,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "date": self.date,
            "time": self.time,
            "observed_temperature": self.observed_temperature,
            "categories": self.categories,
            "granularity": self.granularity,
            "polygon_summary": self.polygon_summary,
            "polygon_aoi": self.polygon_aoi,
            "status": self.status,
            "summary": self.summary,
            "metrics": self.metrics,
            "insights": self.insights,
            "tags": self.tags,
            "pinned": self.pinned,
            "result_cached": self.result_cached,
        }


def _make_record(
    analysis_id: str = "test-001",
    location: str = "Test Location",
    date: str = "2025-06-01",
    metrics: dict | None = None,
    observed_temperature: float | None = None,
    analysis_type: str = "heatmap",
    status: str = "Completed",
) -> FakeAnalysisRecord:
    return FakeAnalysisRecord(
        analysis_id=analysis_id,
        location_label=location,
        date=date,
        metrics=metrics or {},
        observed_temperature=observed_temperature,
        analysis_type=analysis_type,
        status=status,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. calculate_delta — Pure Math
# ══════════════════════════════════════════════════════════════════════════════


class TestCalculateDelta:
    """Pure math: delta and percent_change calculations."""

    def test_basic_positive_delta(self):
        delta, pct = calculate_delta(30.0, 35.0)
        assert delta == 5.0
        assert pct is not None
        assert abs(pct - 16.67) < 0.1

    def test_basic_negative_delta(self):
        delta, pct = calculate_delta(35.0, 30.0)
        assert delta == -5.0
        assert pct is not None
        assert abs(pct - (-14.29)) < 0.1

    def test_zero_delta(self):
        delta, pct = calculate_delta(42.0, 42.0)
        assert delta == 0.0
        assert pct == 0.0

    def test_none_baseline_returns_none(self):
        delta, pct = calculate_delta(None, 35.0)
        assert delta is None
        assert pct is None

    def test_none_comparison_returns_none(self):
        delta, pct = calculate_delta(30.0, None)
        assert delta is None
        assert pct is None

    def test_both_none_returns_none(self):
        delta, pct = calculate_delta(None, None)
        assert delta is None
        assert pct is None

    def test_nan_baseline_returns_none(self):
        delta, pct = calculate_delta(float("nan"), 35.0)
        assert delta is None
        assert pct is None

    def test_nan_comparison_returns_none(self):
        delta, pct = calculate_delta(30.0, float("nan"))
        assert delta is None
        assert pct is None

    def test_inf_baseline_returns_none(self):
        delta, pct = calculate_delta(float("inf"), 35.0)
        assert delta is None
        assert pct is None

    def test_inf_comparison_returns_none(self):
        delta, pct = calculate_delta(30.0, float("inf"))
        assert delta is None
        assert pct is None

    def test_negative_inf_returns_none(self):
        delta, pct = calculate_delta(float("-inf"), 35.0)
        assert delta is None
        assert pct is None

    def test_zero_baseline_no_divide_by_zero(self):
        delta, pct = calculate_delta(0.0, 10.0)
        assert delta == 10.0
        assert pct is None  # Cannot compute % change from 0

    def test_near_zero_baseline(self):
        delta, pct = calculate_delta(1e-12, 10.0)
        assert delta is not None
        assert pct is None  # abs(baseline) < 1e-9

    def test_integer_inputs(self):
        delta, pct = calculate_delta(30, 40)
        assert delta == 10.0
        assert pct is not None

    def test_string_values_return_none(self):
        delta, pct = calculate_delta("hot", "cold")
        assert delta is None
        assert pct is None

    def test_large_values(self):
        delta, pct = calculate_delta(1000000.0, 1000005.0)
        assert delta == 5.0
        assert pct is not None
        assert abs(pct) < 0.01  # tiny percentage

    def test_negative_values(self):
        delta, pct = calculate_delta(-10.0, -5.0)
        assert delta == 5.0
        assert pct is not None


# ══════════════════════════════════════════════════════════════════════════════
# 2. classify_direction — Threshold Classification
# ══════════════════════════════════════════════════════════════════════════════


class TestClassifyDirection:
    """Direction classification with tolerance thresholds."""

    def test_increase_above_tolerance(self):
        assert classify_direction(0.5, tolerance=0.1) == "increase"

    def test_decrease_below_tolerance(self):
        assert classify_direction(-0.5, tolerance=0.1) == "decrease"

    def test_unchanged_within_tolerance(self):
        assert classify_direction(0.05, tolerance=0.1) == "unchanged"

    def test_unchanged_negative_within_tolerance(self):
        assert classify_direction(-0.05, tolerance=0.1) == "unchanged"

    def test_exactly_at_tolerance_is_unchanged(self):
        assert classify_direction(0.1, tolerance=0.1) == "unchanged"

    def test_exactly_at_negative_tolerance_is_unchanged(self):
        assert classify_direction(-0.1, tolerance=0.1) == "unchanged"

    def test_none_delta_is_insufficient_data(self):
        assert classify_direction(None) == "insufficient_data"

    def test_nan_delta_is_insufficient_data(self):
        assert classify_direction(float("nan")) == "insufficient_data"

    def test_inf_delta_is_insufficient_data(self):
        assert classify_direction(float("inf")) == "insufficient_data"

    def test_zero_tolerance(self):
        assert classify_direction(0.001, tolerance=0.0) == "increase"
        assert classify_direction(-0.001, tolerance=0.0) == "decrease"
        assert classify_direction(0.0, tolerance=0.0) == "unchanged"


# ══════════════════════════════════════════════════════════════════════════════
# 3. build_comparison_metric — Single Metric Builder
# ══════════════════════════════════════════════════════════════════════════════


class TestBuildComparisonMetric:
    """Tests for building individual comparison metrics from record dicts."""

    def test_available_metric_positive_delta(self):
        baseline = {"metrics": {"mean_temp": 30.0}}
        comparison = {"metrics": {"mean_temp": 35.0}}

        m = build_comparison_metric(
            key="mean_temperature",
            label="Mean Temperature",
            unit="°C",
            baseline_record=baseline,
            comparison_record=comparison,
            candidate_keys=["mean_temp", "mean_temperature"],
            tolerance=0.1,
            increase_phrase="Warmer.",
            decrease_phrase="Cooler.",
            unchanged_phrase="Same.",
        )

        assert m.available is True
        assert m.direction == "increase"
        assert m.delta is not None
        assert abs(m.delta - 5.0) < 0.01
        assert m.label == "Mean Temperature"
        assert m.unit == "°C"
        assert "Warmer" in m.interpretation

    def test_available_metric_negative_delta(self):
        baseline = {"metrics": {"mean_temp": 40.0}}
        comparison = {"metrics": {"mean_temp": 32.0}}

        m = build_comparison_metric(
            key="mean_temperature",
            label="Mean Temperature",
            unit="°C",
            baseline_record=baseline,
            comparison_record=comparison,
            candidate_keys=["mean_temp"],
            tolerance=0.1,
            increase_phrase="Warmer.",
            decrease_phrase="Cooler.",
            unchanged_phrase="Same.",
        )

        assert m.available is True
        assert m.direction == "decrease"
        assert m.delta < 0

    def test_unavailable_metric_baseline_missing(self):
        baseline = {"metrics": {}}
        comparison = {"metrics": {"mean_temp": 35.0}}

        m = build_comparison_metric(
            key="mean_temperature",
            label="Mean Temperature",
            unit="°C",
            baseline_record=baseline,
            comparison_record=comparison,
            candidate_keys=["mean_temp"],
            tolerance=0.1,
            increase_phrase="Warmer.",
            decrease_phrase="Cooler.",
            unchanged_phrase="Same.",
        )

        assert m.available is False
        assert m.direction == "insufficient_data"
        assert m.delta is None

    def test_unavailable_metric_comparison_missing(self):
        baseline = {"metrics": {"mean_temp": 35.0}}
        comparison = {"metrics": {}}

        m = build_comparison_metric(
            key="mean_temperature",
            label="Mean Temperature",
            unit="°C",
            baseline_record=baseline,
            comparison_record=comparison,
            candidate_keys=["mean_temp"],
            tolerance=0.1,
            increase_phrase="Warmer.",
            decrease_phrase="Cooler.",
            unchanged_phrase="Same.",
        )

        assert m.available is False
        assert m.direction == "insufficient_data"

    def test_metric_within_tolerance_unchanged(self):
        baseline = {"metrics": {"mean_temp": 30.0}}
        comparison = {"metrics": {"mean_temp": 30.05}}

        m = build_comparison_metric(
            key="mean_temperature",
            label="Mean Temperature",
            unit="°C",
            baseline_record=baseline,
            comparison_record=comparison,
            candidate_keys=["mean_temp"],
            tolerance=0.1,
            increase_phrase="Warmer.",
            decrease_phrase="Cooler.",
            unchanged_phrase="Same.",
        )

        assert m.available is True
        assert m.direction == "unchanged"
        assert "Same" in m.interpretation

    def test_metric_extraction_uses_fallback_keys(self):
        """Verifies alternative key resolution from candidate_keys list."""
        baseline = {"metrics": {"temperature": 28.0}}
        comparison = {"metrics": {"temperature": 33.0}}

        m = build_comparison_metric(
            key="mean_temperature",
            label="Mean Temperature",
            unit="°C",
            baseline_record=baseline,
            comparison_record=comparison,
            candidate_keys=["mean_temp", "mean_temperature", "temperature"],
            tolerance=0.1,
            increase_phrase="Warmer.",
            decrease_phrase="Cooler.",
            unchanged_phrase="Same.",
        )

        assert m.available is True
        assert m.delta is not None

    def test_metric_extraction_from_top_level_keys(self):
        """Metric can also be found at top-level of record dict."""
        baseline = {"observed_temperature": 29.0}
        comparison = {"observed_temperature": 34.0}

        m = build_comparison_metric(
            key="mean_temperature",
            label="Mean Temperature",
            unit="°C",
            baseline_record=baseline,
            comparison_record=comparison,
            candidate_keys=["observed_temperature"],
            tolerance=0.1,
            increase_phrase="Warmer.",
            decrease_phrase="Cooler.",
            unchanged_phrase="Same.",
        )

        assert m.available is True
        assert abs(m.delta - 5.0) < 0.01

    def test_to_dict_returns_all_fields(self):
        m = ComparisonMetric(
            key="test",
            label="Test Metric",
            baseline_value=10.0,
            comparison_value=15.0,
            delta=5.0,
            percent_change=50.0,
            unit="°C",
            direction="increase",
            interpretation="Increased.",
            evidence="10 → 15",
            available=True,
        )
        d = m.to_dict()
        assert d["key"] == "test"
        assert d["label"] == "Test Metric"
        assert d["delta"] == 5.0
        assert d["available"] is True
        assert "direction" in d
        assert "evidence" in d


# ══════════════════════════════════════════════════════════════════════════════
# 4. compare_analysis_records — End-to-End Comparison
# ══════════════════════════════════════════════════════════════════════════════


class TestCompareAnalysisRecords:
    """Integration tests for full record comparison."""

    def test_comparison_with_full_metrics(self):
        rec_a = _make_record(
            analysis_id="A-001",
            location="Downtown",
            date="2025-06-01",
            metrics={
                "mean_temp": 34.5,
                "min_temp": 28.0,
                "max_temp": 41.0,
                "temp_spread": 13.0,
                "total_tiles": 120,
            },
        )
        rec_b = _make_record(
            analysis_id="B-001",
            location="Downtown",
            date="2025-06-15",
            metrics={
                "mean_temp": 36.0,
                "min_temp": 29.5,
                "max_temp": 42.5,
                "temp_spread": 13.0,
                "total_tiles": 120,
            },
        )

        result = compare_analysis_records(rec_a, rec_b)

        assert result["baseline_id"] == "A-001"
        assert result["comparison_id"] == "B-001"
        assert len(result["metrics"]) == 6  # 6 candidate metrics
        assert isinstance(result["increased"], list)
        assert isinstance(result["decreased"], list)
        assert isinstance(result["unchanged"], list)
        assert isinstance(result["missing"], list)
        assert "headline" in result
        assert "data_quality" in result

    def test_comparison_headline_increase(self):
        rec_a = _make_record(metrics={"mean_temp": 30.0})
        rec_b = _make_record(metrics={"mean_temp": 35.0})

        result = compare_analysis_records(rec_a, rec_b)
        assert "Warmer" in result["headline"]

    def test_comparison_headline_decrease(self):
        rec_a = _make_record(metrics={"mean_temp": 35.0})
        rec_b = _make_record(metrics={"mean_temp": 30.0})

        result = compare_analysis_records(rec_a, rec_b)
        assert "Cooler" in result["headline"]

    def test_comparison_headline_unchanged(self):
        rec_a = _make_record(metrics={"mean_temp": 30.0})
        rec_b = _make_record(metrics={"mean_temp": 30.05})

        result = compare_analysis_records(rec_a, rec_b)
        assert "consistent" in result["headline"].lower()

    def test_comparison_data_quality_all_available(self):
        rec_a = _make_record(
            metrics={
                "mean_temp": 30.0,
                "min_temp": 25.0,
                "max_temp": 35.0,
                "temp_spread": 10.0,
                "total_tiles": 100,
                "above_threshold_proportion": 0.3,
            },
        )
        rec_b = _make_record(
            metrics={
                "mean_temp": 32.0,
                "min_temp": 27.0,
                "max_temp": 37.0,
                "temp_spread": 10.0,
                "total_tiles": 100,
                "above_threshold_proportion": 0.4,
            },
        )

        result = compare_analysis_records(rec_a, rec_b)
        dq = result["data_quality"]
        assert dq["metrics_available"] == 6
        assert dq["missing_count"] == 0

    def test_comparison_data_quality_partial(self):
        rec_a = _make_record(metrics={"mean_temp": 30.0})
        rec_b = _make_record(metrics={"mean_temp": 35.0})

        result = compare_analysis_records(rec_a, rec_b)
        dq = result["data_quality"]
        assert dq["metrics_available"] >= 1
        assert dq["missing_count"] >= 1

    def test_comparison_no_common_metrics(self):
        rec_a = _make_record(metrics={})
        rec_b = _make_record(metrics={})

        result = compare_analysis_records(rec_a, rec_b)
        assert all(not m.available for m in result["metrics"])
        assert "Insufficient" in result["headline"]

    def test_comparison_includes_disclaimer(self):
        rec_a = _make_record(metrics={"mean_temp": 30.0})
        rec_b = _make_record(metrics={"mean_temp": 35.0})

        result = compare_analysis_records(rec_a, rec_b)
        assert result["disclaimer"] == RESPONSIBLE_ANALYTICS_DISCLAIMER

    def test_comparison_uses_dict_records(self):
        """Works with plain dicts instead of AnalysisRecord objects."""
        dict_a = {
            "analysis_id": "D-001",
            "location_label": "Loc A",
            "date": "2025-01-01",
            "metrics": {"mean_temp": 28.0},
        }
        dict_b = {
            "analysis_id": "D-002",
            "location_label": "Loc B",
            "date": "2025-01-02",
            "metrics": {"mean_temp": 33.0},
        }

        result = compare_analysis_records(dict_a, dict_b)
        assert result["baseline_id"] == "D-001"
        assert result["comparison_id"] == "D-002"

    def test_comparison_direction_counts(self):
        rec_a = _make_record(
            metrics={
                "mean_temp": 30.0,
                "min_temp": 25.0,
                "max_temp": 35.0,
            },
        )
        rec_b = _make_record(
            metrics={
                "mean_temp": 35.0,  # +5 = increase
                "min_temp": 25.0,   # 0 = unchanged
                "max_temp": 30.0,   # -5 = decrease
            },
        )

        result = compare_analysis_records(rec_a, rec_b)
        assert len(result["increased"]) >= 1
        assert len(result["unchanged"]) >= 1
        assert len(result["decreased"]) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# 5. Responsible Analytics Invariants
# ══════════════════════════════════════════════════════════════════════════════


class TestResponsibleAnalytics:
    """Verify no causal, medical, or forecast language appears in outputs."""

    FORBIDDEN_TERMS = [
        "caused by",
        "due to",
        "hazardous",
        "fatal",
        "deadly",
        "will cause",
        "prediction",
        "forecast",
        "diagnosis",
        "health risk",
    ]

    def test_disclaimer_text_is_neutral(self):
        disclaimer = RESPONSIBLE_ANALYTICS_DISCLAIMER
        for term in self.FORBIDDEN_TERMS:
            assert term.lower() not in disclaimer.lower(), f"Forbidden term '{term}' found in disclaimer"

    def test_comparison_interpretations_are_neutral(self):
        rec_a = _make_record(
            metrics={
                "mean_temp": 30.0,
                "min_temp": 25.0,
                "max_temp": 35.0,
                "temp_spread": 10.0,
                "total_tiles": 100,
            },
        )
        rec_b = _make_record(
            metrics={
                "mean_temp": 40.0,
                "min_temp": 30.0,
                "max_temp": 50.0,
                "temp_spread": 20.0,
                "total_tiles": 200,
            },
        )

        result = compare_analysis_records(rec_a, rec_b)

        for m in result["metrics"]:
            for term in self.FORBIDDEN_TERMS:
                assert term.lower() not in m.interpretation.lower(), (
                    f"Forbidden term '{term}' found in metric interpretation: {m.interpretation}"
                )

    def test_headline_is_neutral(self):
        rec_a = _make_record(metrics={"mean_temp": 25.0})
        rec_b = _make_record(metrics={"mean_temp": 50.0})

        result = compare_analysis_records(rec_a, rec_b)
        for term in self.FORBIDDEN_TERMS:
            assert term.lower() not in result["headline"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# 6. ComparisonMetric Immutability & Frozen
# ══════════════════════════════════════════════════════════════════════════════


class TestComparisonMetricImmutability:
    """ComparisonMetric is frozen — attributes cannot be mutated."""

    def test_frozen_raises_on_mutation(self):
        m = ComparisonMetric(
            key="test",
            label="Test",
            baseline_value=1.0,
            comparison_value=2.0,
            delta=1.0,
            percent_change=100.0,
            unit="°C",
            direction="increase",
            interpretation="Higher.",
            evidence="1→2",
        )
        with pytest.raises(AttributeError):
            m.delta = 999.0  # type: ignore[misc]


# ══════════════════════════════════════════════════════════════════════════════
# 7. Threshold Constants
# ══════════════════════════════════════════════════════════════════════════════


class TestDecisionThresholds:
    """Ensure threshold constants are defined and reasonable."""

    def test_temperature_tolerance_exists(self):
        assert "temperature_tolerance_deg_c" in DECISION_THRESHOLDS
        assert DECISION_THRESHOLDS["temperature_tolerance_deg_c"] > 0

    def test_spread_tolerance_exists(self):
        assert "temperature_spread_tolerance_deg_c" in DECISION_THRESHOLDS

    def test_tile_count_tolerance_exists(self):
        assert "tile_count_tolerance" in DECISION_THRESHOLDS

    def test_proportion_tolerance_exists(self):
        assert "proportion_tolerance" in DECISION_THRESHOLDS
