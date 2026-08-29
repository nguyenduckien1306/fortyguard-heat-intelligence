"""Comparative analysis utilities for Heatmap results.

Enables side-by-side comparison and delta calculations between compatible
completed Heatmap analyses within the session.
"""

from __future__ import annotations

from typing import Any, Mapping


def can_compare_heatmap_analyses(
    analysis_a: Mapping[str, Any],
    analysis_b: Mapping[str, Any],
) -> tuple[bool, str]:
    """
    Validate whether two analysis entries have sufficient compatible data for comparison.

    Returns (is_compatible, reason_message).
    """
    type_a = analysis_a.get("analysis_type", "").lower()
    type_b = analysis_b.get("analysis_type", "").lower()

    if "heatmap" not in type_a or "heatmap" not in type_b:
        return False, "Only Heatmap analyses can be compared numerically."

    status_a = analysis_a.get("status", "")
    status_b = analysis_b.get("status", "")

    if status_a != "Completed" or status_b != "Completed":
        return False, "Both analyses must be in 'Completed' status for comparison."

    metrics_a = analysis_a.get("metrics_summary") or {}
    metrics_b = analysis_b.get("metrics_summary") or {}

    if not metrics_a or not metrics_b:
        return False, "These analyses do not contain enough compatible temperature data for comparison."

    return True, "Analyses are compatible for comparison."


def compare_heatmap_analyses(
    analysis_a: Mapping[str, Any],
    analysis_b: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Perform metric-by-metric comparison and delta calculations between two Heatmap analyses.

    Delta is defined as: Analysis B - Analysis A.
    """
    metrics_a = analysis_a.get("metrics_summary") or {}
    metrics_b = analysis_b.get("metrics_summary") or {}

    compared_metrics: list[dict[str, Any]] = []

    metric_defs = [
        ("mean_temp", "Mean Temperature", "°C", 2),
        ("min_temp", "Minimum Temperature", "°C", 2),
        ("max_temp", "Maximum Temperature", "°C", 2),
        ("temp_spread", "Temperature Spread", "°C", 2),
        ("tile_count", "Spatial Tile Count", "tiles", 0),
    ]

    for key, label, unit, precision in metric_defs:
        val_a = metrics_a.get(key)
        val_b = metrics_b.get(key)

        if val_a is not None and val_b is not None:
            try:
                num_a = float(val_a)
                num_b = float(val_b)
                diff = round(num_b - num_a, precision) if precision > 0 else (num_b - num_a)
                
                if precision == 0:
                    diff_str = f"{int(diff):+d} {unit}"
                    val_a_str = f"{int(num_a)} {unit}"
                    val_b_str = f"{int(num_b)} {unit}"
                else:
                    diff_str = f"{diff:+.{precision}f} {unit}"
                    val_a_str = f"{num_a:.{precision}f} {unit}"
                    val_b_str = f"{num_b:.{precision}f} {unit}"

                compared_metrics.append({
                    "metric_key": key,
                    "label": label,
                    "value_a": val_a_str,
                    "value_b": val_b_str,
                    "raw_a": num_a,
                    "raw_b": num_b,
                    "raw_diff": diff,
                    "diff_formatted": diff_str,
                    "unit": unit,
                })
            except (ValueError, TypeError):
                continue

    # Generate per-metric interpretations
    _INTERPRETATIONS: dict[str, tuple[str, str]] = {
        "mean_temp": ("Warmer in B", "Cooler in B"),
        "min_temp": ("Higher minimum in B", "Lower minimum in B"),
        "max_temp": ("Higher maximum in B", "Lower maximum in B"),
        "temp_spread": ("Wider range in B", "Narrower range in B"),
        "tile_count": ("More tiles in B", "Fewer tiles in B"),
    }

    for m in compared_metrics:
        key = m["metric_key"]
        diff = m["raw_diff"]
        higher, lower = _INTERPRETATIONS.get(key, ("Higher in B", "Lower in B"))
        if diff > 0:
            m["interpretation"] = higher
        elif diff < 0:
            m["interpretation"] = lower
        else:
            m["interpretation"] = "No difference"

    return {
        "analysis_a_id": analysis_a.get("activity_id", "A"),
        "analysis_a_label": analysis_a.get("label", "Analysis A"),
        "analysis_b_id": analysis_b.get("activity_id", "B"),
        "analysis_b_label": analysis_b.get("label", "Analysis B"),
        "compared_metrics": compared_metrics,
        "is_valid": len(compared_metrics) > 0,
    }
