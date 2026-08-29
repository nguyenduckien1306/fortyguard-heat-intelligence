"""Tests for the Heatmap comparative analytics utility."""

from __future__ import annotations

from frontend.utils.comparison import can_compare_heatmap_analyses, compare_heatmap_analyses


_ANALYSIS_A = {
    "analysis_type": "Heatmap",
    "activity_id": "act-cmp-A",
    "label": "Manhattan Day 1",
    "status": "Completed",
    "metrics_summary": {
        "mean_temp": 32.26,
        "min_temp": 31.89,
        "max_temp": 33.14,
        "temp_spread": 1.25,
        "tile_count": 150,
    },
}

_ANALYSIS_B = {
    "analysis_type": "Heatmap",
    "activity_id": "act-cmp-B",
    "label": "Manhattan Day 2",
    "status": "Completed",
    "metrics_summary": {
        "mean_temp": 31.44,
        "min_temp": 30.91,
        "max_temp": 32.01,
        "temp_spread": 1.10,
        "tile_count": 150,
    },
}


def test_can_compare_compatible_analyses() -> None:
    ok, msg = can_compare_heatmap_analyses(_ANALYSIS_A, _ANALYSIS_B)
    assert ok is True


def test_can_compare_incompatible_types() -> None:
    hi_entry = {
        "analysis_type": "Heat Intelligence",
        "status": "Completed",
        "metrics_summary": {},
    }
    ok, msg = can_compare_heatmap_analyses(_ANALYSIS_A, hi_entry)
    assert ok is False
    assert "Only Heatmap" in msg


def test_can_compare_incompatible_status() -> None:
    proc_entry = {
        "analysis_type": "Heatmap",
        "status": "Processing",
        "metrics_summary": {},
    }
    ok, msg = can_compare_heatmap_analyses(_ANALYSIS_A, proc_entry)
    assert ok is False
    assert "Completed" in msg


def test_compare_heatmap_analyses_calculates_deltas() -> None:
    comparison = compare_heatmap_analyses(_ANALYSIS_A, _ANALYSIS_B)
    assert comparison["is_valid"] is True
    assert comparison["analysis_a_id"] == "act-cmp-A"
    assert comparison["analysis_b_id"] == "act-cmp-B"

    metrics = {m["metric_key"]: m for m in comparison["compared_metrics"]}

    # Mean temp: 31.44 - 32.26 = -0.82
    assert metrics["mean_temp"]["raw_diff"] == round(31.44 - 32.26, 2)
    assert "-0.82 °C" in metrics["mean_temp"]["diff_formatted"]

    # Min temp: 30.91 - 31.89 = -0.98
    assert "-0.98 °C" in metrics["min_temp"]["diff_formatted"]

    # Max temp: 32.01 - 33.14 = -1.13
    assert "-1.13 °C" in metrics["max_temp"]["diff_formatted"]

    # Tile count: 150 - 150 = 0
    assert "+0 tiles" in metrics["tile_count"]["diff_formatted"]


def test_compare_heatmap_analyses_handles_missing_individual_metric() -> None:
    partial_a = {
        "analysis_type": "Heatmap",
        "status": "Completed",
        "metrics_summary": {"mean_temp": 30.0},
    }
    partial_b = {
        "analysis_type": "Heatmap",
        "status": "Completed",
        "metrics_summary": {"mean_temp": 32.0, "max_temp": 35.0},
    }
    comparison = compare_heatmap_analyses(partial_a, partial_b)
    assert len(comparison["compared_metrics"]) == 1
    assert comparison["compared_metrics"][0]["metric_key"] == "mean_temp"


# ── Phase 10: Comparison interpretations ──


def test_comparison_interpretation_positive_delta() -> None:
    comparison = compare_heatmap_analyses(_ANALYSIS_B, _ANALYSIS_A)
    # B→A: mean goes from 31.44→32.26 = positive delta
    metrics = {m["metric_key"]: m for m in comparison["compared_metrics"]}
    assert metrics["mean_temp"]["interpretation"] == "Warmer in B"


def test_comparison_interpretation_negative_delta() -> None:
    comparison = compare_heatmap_analyses(_ANALYSIS_A, _ANALYSIS_B)
    metrics = {m["metric_key"]: m for m in comparison["compared_metrics"]}
    assert metrics["mean_temp"]["interpretation"] == "Cooler in B"


def test_comparison_interpretation_zero_delta() -> None:
    same = {
        "analysis_type": "Heatmap",
        "activity_id": "same",
        "status": "Completed",
        "metrics_summary": {"mean_temp": 30.0, "tile_count": 100},
    }
    comparison = compare_heatmap_analyses(same, same)
    metrics = {m["metric_key"]: m for m in comparison["compared_metrics"]}
    assert metrics["mean_temp"]["interpretation"] == "No difference"
    assert metrics["tile_count"]["interpretation"] == "No difference"


def test_comparison_spread_interpretation() -> None:
    a = {
        "analysis_type": "Heatmap",
        "activity_id": "a",
        "status": "Completed",
        "metrics_summary": {"temp_spread": 2.0},
    }
    b = {
        "analysis_type": "Heatmap",
        "activity_id": "b",
        "status": "Completed",
        "metrics_summary": {"temp_spread": 1.0},
    }
    comparison = compare_heatmap_analyses(a, b)
    metrics = {m["metric_key"]: m for m in comparison["compared_metrics"]}
    assert metrics["temp_spread"]["interpretation"] == "Narrower range in B"
