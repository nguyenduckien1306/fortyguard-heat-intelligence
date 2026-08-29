"""Exhaustive tests for the Analytical Insight Engine.

Covers variability classification, data quality, above-threshold proportion,
heatmap insight generation, comparison insights, severity helpers, and
format summary — including all boundary values and edge cases.
"""

from __future__ import annotations

from frontend.utils.insights import (
    ANALYTICS_DISCLAIMER,
    Insight,
    InsightSeverity,
    calculate_above_threshold_proportion,
    classify_data_quality,
    classify_temperature_variability,
    format_insight_summary,
    generate_comparison_insights,
    generate_heatmap_insights,
    insight_severity_to_icon,
    insight_severity_to_label,
)


# ──────────────────────────────────────────────────────────────────────────────
# Variability classification — exact boundary tests
# ──────────────────────────────────────────────────────────────────────────────


def test_variability_below_0_5() -> None:
    label, sev = classify_temperature_variability(0.49)
    assert label == "Very Low"
    assert sev == InsightSeverity.INFO


def test_variability_at_0_5() -> None:
    label, sev = classify_temperature_variability(0.50)
    assert label == "Low"
    assert sev == InsightSeverity.INFO


def test_variability_below_2_0() -> None:
    label, sev = classify_temperature_variability(1.99)
    assert label == "Low"
    assert sev == InsightSeverity.INFO


def test_variability_at_2_0() -> None:
    label, sev = classify_temperature_variability(2.00)
    assert label == "Moderate"
    assert sev == InsightSeverity.ATTENTION


def test_variability_below_5_0() -> None:
    label, sev = classify_temperature_variability(4.99)
    assert label == "Moderate"
    assert sev == InsightSeverity.ATTENTION


def test_variability_at_5_0() -> None:
    label, sev = classify_temperature_variability(5.00)
    assert label == "High"
    assert sev == InsightSeverity.ATTENTION


def test_variability_zero_spread() -> None:
    label, _ = classify_temperature_variability(0.0)
    assert label == "Very Low"


def test_variability_none() -> None:
    label, sev = classify_temperature_variability(None)
    assert label == "Insufficient Data"
    assert sev == InsightSeverity.WARNING


def test_variability_negative_temperature_spread() -> None:
    # Negative spread shouldn't occur naturally, but engine must not crash
    label, _ = classify_temperature_variability(-1.0)
    assert label == "Very Low"


# ──────────────────────────────────────────────────────────────────────────────
# Data quality classification
# ──────────────────────────────────────────────────────────────────────────────


def test_data_quality_complete() -> None:
    label, sev = classify_data_quality(total=100, valid=100)
    assert label == "Complete"
    assert sev == InsightSeverity.POSITIVE


def test_data_quality_mostly_complete() -> None:
    label, sev = classify_data_quality(total=100, valid=95)
    assert label == "Mostly Complete"
    assert sev == InsightSeverity.INFO


def test_data_quality_partial() -> None:
    label, sev = classify_data_quality(total=100, valid=60)
    assert label == "Partial"
    assert sev == InsightSeverity.ATTENTION


def test_data_quality_insufficient() -> None:
    label, sev = classify_data_quality(total=100, valid=30)
    assert label == "Insufficient"
    assert sev == InsightSeverity.WARNING


def test_data_quality_zero_tiles() -> None:
    label, sev = classify_data_quality(total=0, valid=0)
    assert label == "Insufficient"


def test_data_quality_none_total() -> None:
    label, sev = classify_data_quality(total=None, valid=50)
    assert label == "Insufficient"


def test_data_quality_from_missing_count() -> None:
    label, sev = classify_data_quality(total=100, valid=None, missing=5)
    assert label == "Mostly Complete"


# ──────────────────────────────────────────────────────────────────────────────
# Above-threshold tile proportion
# ──────────────────────────────────────────────────────────────────────────────


def test_above_threshold_basic() -> None:
    temps = [30.0, 31.0, 32.0, 33.0, 34.0]
    result = calculate_above_threshold_proportion(temps, 32.0)
    # 33.0 and 34.0 are above 32.0 → 2/5 = 0.4
    assert result == 0.4


def test_above_threshold_all_above() -> None:
    temps = [35.0, 36.0, 37.0]
    result = calculate_above_threshold_proportion(temps, 30.0)
    assert result == 1.0


def test_above_threshold_none_above() -> None:
    temps = [20.0, 21.0]
    result = calculate_above_threshold_proportion(temps, 25.0)
    assert result == 0.0


def test_above_threshold_empty_list() -> None:
    result = calculate_above_threshold_proportion([], 30.0)
    assert result is None


def test_above_threshold_with_none_values() -> None:
    temps = [30.0, None, 35.0, None]
    result = calculate_above_threshold_proportion(temps, 32.0)
    # 35.0 above 32.0 → 1/2 valid = 0.5
    assert result == 0.5


def test_above_threshold_with_nan_and_inf() -> None:
    import math
    temps = [30.0, float("nan"), float("inf"), 35.0]
    result = calculate_above_threshold_proportion(temps, 32.0)
    # Only 30.0 and 35.0 valid; 35.0 above 32.0 → 1/2 = 0.5
    assert result == 0.5


def test_above_threshold_single_value() -> None:
    result = calculate_above_threshold_proportion([40.0], 30.0)
    assert result == 1.0


def test_above_threshold_duplicate_values() -> None:
    result = calculate_above_threshold_proportion([30.0, 30.0, 30.0], 30.0)
    # None above 30.0 (strictly greater)
    assert result == 0.0


def test_above_threshold_negative_temps() -> None:
    temps = [-5.0, -3.0, -1.0, 1.0]
    result = calculate_above_threshold_proportion(temps, 0.0)
    # Only 1.0 above 0.0 → 1/4 = 0.25
    assert result == 0.25


# ──────────────────────────────────────────────────────────────────────────────
# Heatmap insight generation
# ──────────────────────────────────────────────────────────────────────────────


def test_generate_heatmap_insights_normal_data() -> None:
    metrics = {
        "total_tiles": 150,
        "valid_tiles_count": 148,
        "missing_tiles_count": 2,
        "min_temp": 30.50,
        "max_temp": 34.20,
        "mean_temp": 32.26,
        "temp_spread": 3.70,
        "hottest_tile": {"tile_id": 87, "temperature": 34.20},
        "coolest_tile": {"tile_id": 12, "temperature": 30.50},
    }
    insights = generate_heatmap_insights(metrics)
    assert len(insights) >= 5

    categories = [i.category for i in insights]
    assert "Coverage" in categories
    assert "Data Quality" in categories
    assert "Variability" in categories
    assert "Extremes" in categories

    # Verify hottest tile insight
    hottest_ins = [i for i in insights if i.title == "Hottest Tile"]
    assert len(hottest_ins) == 1
    assert "Tile 87" in hottest_ins[0].summary
    assert "34.20 °C" in hottest_ins[0].summary


def test_generate_heatmap_insights_complete_data() -> None:
    metrics = {
        "total_tiles": 50,
        "valid_tiles_count": 50,
        "missing_tiles_count": 0,
        "min_temp": 20.0,
        "max_temp": 20.0,
        "mean_temp": 20.0,
        "temp_spread": 0.0,
        "hottest_tile": {"tile_id": 1, "temperature": 20.0},
        "coolest_tile": {"tile_id": 1, "temperature": 20.0},
    }
    insights = generate_heatmap_insights(metrics)
    # Should have POSITIVE data quality insight
    quality_ins = [i for i in insights if i.category == "Data Quality"]
    assert quality_ins[0].severity == InsightSeverity.POSITIVE
    # Variability should be Very Low
    var_ins = [i for i in insights if i.category == "Variability"]
    assert "very low" in var_ins[0].summary.lower()


def test_generate_heatmap_insights_none_input() -> None:
    insights = generate_heatmap_insights(None)
    assert len(insights) == 1
    assert insights[0].severity == InsightSeverity.WARNING


def test_generate_heatmap_insights_empty_dict() -> None:
    insights = generate_heatmap_insights({})
    assert len(insights) == 1
    assert insights[0].severity == InsightSeverity.WARNING


def test_generate_heatmap_insights_missing_spread() -> None:
    metrics = {
        "total_tiles": 5,
        "valid_tiles_count": 0,
        "missing_tiles_count": 5,
        "min_temp": None,
        "max_temp": None,
        "mean_temp": None,
        "temp_spread": None,
        "hottest_tile": None,
        "coolest_tile": None,
    }
    insights = generate_heatmap_insights(metrics)
    # Should have coverage and quality but no variability or extremes
    categories = [i.category for i in insights]
    assert "Coverage" in categories
    assert "Variability" not in categories


# ──────────────────────────────────────────────────────────────────────────────
# Comparison insight generation
# ──────────────────────────────────────────────────────────────────────────────


def test_generate_comparison_insights_positive_delta() -> None:
    comparison = {
        "is_valid": True,
        "analysis_a_label": "Day 1",
        "analysis_b_label": "Day 2",
        "compared_metrics": [
            {
                "metric_key": "mean_temp",
                "label": "Mean Temperature",
                "value_a": "31.00 °C",
                "value_b": "33.00 °C",
                "raw_diff": 2.0,
                "diff_formatted": "+2.00 °C",
                "unit": "°C",
            }
        ],
    }
    insights = generate_comparison_insights(comparison)
    assert len(insights) == 1
    assert "Warmer in B" in insights[0].summary


def test_generate_comparison_insights_negative_delta() -> None:
    comparison = {
        "is_valid": True,
        "analysis_a_label": "A",
        "analysis_b_label": "B",
        "compared_metrics": [
            {
                "metric_key": "temp_spread",
                "label": "Temperature Spread",
                "value_a": "3.00 °C",
                "value_b": "1.50 °C",
                "raw_diff": -1.5,
                "diff_formatted": "-1.50 °C",
                "unit": "°C",
            }
        ],
    }
    insights = generate_comparison_insights(comparison)
    assert "Narrower range in B" in insights[0].summary


def test_generate_comparison_insights_zero_delta() -> None:
    comparison = {
        "is_valid": True,
        "analysis_a_label": "A",
        "analysis_b_label": "B",
        "compared_metrics": [
            {
                "metric_key": "tile_count",
                "label": "Spatial Tile Count",
                "value_a": "150 tiles",
                "value_b": "150 tiles",
                "raw_diff": 0,
                "diff_formatted": "+0 tiles",
                "unit": "tiles",
            }
        ],
    }
    insights = generate_comparison_insights(comparison)
    assert "No difference" in insights[0].summary


def test_generate_comparison_insights_invalid_result() -> None:
    assert generate_comparison_insights(None) == []
    assert generate_comparison_insights({"is_valid": False}) == []


# ──────────────────────────────────────────────────────────────────────────────
# Severity helpers
# ──────────────────────────────────────────────────────────────────────────────


def test_severity_icons() -> None:
    assert insight_severity_to_icon(InsightSeverity.INFO) == "ℹ️"
    assert insight_severity_to_icon(InsightSeverity.POSITIVE) == "✅"
    assert insight_severity_to_icon(InsightSeverity.ATTENTION) == "🔶"
    assert insight_severity_to_icon(InsightSeverity.WARNING) == "⚠️"


def test_severity_labels() -> None:
    assert insight_severity_to_label(InsightSeverity.INFO) == "Informational"
    assert insight_severity_to_label(InsightSeverity.POSITIVE) == "Positive"
    assert insight_severity_to_label(InsightSeverity.ATTENTION) == "Attention"
    assert insight_severity_to_label(InsightSeverity.WARNING) == "Data Notice"


# ──────────────────────────────────────────────────────────────────────────────
# Format summary
# ──────────────────────────────────────────────────────────────────────────────


def test_format_insight_summary_empty() -> None:
    assert format_insight_summary([]) == "No analytical insights available."


def test_format_insight_summary_basic() -> None:
    insights = [
        Insight(
            category="Test",
            title="Test Insight",
            severity=InsightSeverity.INFO,
            summary="Something observed.",
            evidence="value = 42",
        )
    ]
    text = format_insight_summary(insights)
    assert "[INFO]" in text
    assert "Test Insight" in text
    assert "Something observed." in text
    assert "value = 42" in text


# ──────────────────────────────────────────────────────────────────────────────
# Disclaimer
# ──────────────────────────────────────────────────────────────────────────────


def test_analytics_disclaimer_exists() -> None:
    assert "descriptive calculations" in ANALYTICS_DISCLAIMER
    assert "not additional FortyGuard classifications" in ANALYTICS_DISCLAIMER


# ──────────────────────────────────────────────────────────────────────────────
# Insight dataclass
# ──────────────────────────────────────────────────────────────────────────────


def test_insight_is_frozen() -> None:
    ins = Insight(
        category="Test",
        title="Frozen",
        severity=InsightSeverity.INFO,
        summary="Immutable.",
    )
    try:
        ins.title = "Changed"  # type: ignore
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass  # Expected — frozen dataclass
