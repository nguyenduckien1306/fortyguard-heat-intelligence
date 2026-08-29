"""Pure Deterministic Decision Intelligence & Comparative Analytics Engine.

Strict Architectural Invariants:
1. Zero Streamlit imports, zero HTTP clients, zero network requests.
2. Pure, deterministic mathematical derivations on confirmed AnalysisRecord data.
3. Never fabricates missing metrics or guesses default values.
4. Never asserts scientific causality, medical consequences, or forecasts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping

# ──────────────────────────────────────────────────────────────────────────────
# Centralized Comparison Thresholds & Tolerances
# ──────────────────────────────────────────────────────────────────────────────

DECISION_THRESHOLDS: dict[str, float] = {
    "temperature_tolerance_deg_c": 0.1,
    "temperature_spread_tolerance_deg_c": 0.2,
    "tile_count_tolerance": 0.0,
    "proportion_tolerance": 0.01,
}

RESPONSIBLE_ANALYTICS_DISCLAIMER: str = (
    "Responsible Analytics: These comparisons are descriptive numerical calculations derived "
    "from confirmed analysis records. They do not establish causation, medical significance, "
    "scientific significance, or FortyGuard classifications."
)


# ──────────────────────────────────────────────────────────────────────────────
# ComparisonMetric Dataclass
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ComparisonMetric:
    """Immutable representation of a pairwise metric comparison."""

    key: str
    label: str
    baseline_value: float | int | str | None
    comparison_value: float | int | str | None
    delta: float | None
    percent_change: float | None
    unit: str
    direction: str  # "increase" | "decrease" | "unchanged" | "insufficient_data"
    interpretation: str
    evidence: str
    available: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "baseline_value": self.baseline_value,
            "comparison_value": self.comparison_value,
            "delta": self.delta,
            "percent_change": self.percent_change,
            "unit": self.unit,
            "direction": self.direction,
            "interpretation": self.interpretation,
            "evidence": self.evidence,
            "available": self.available,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Pure Metric Mathematics
# ──────────────────────────────────────────────────────────────────────────────


def calculate_delta(
    baseline: float | int | None,
    comparison: float | int | None,
) -> tuple[float | None, float | None]:
    """Calculate mathematical difference (comparison - baseline) and percentage change.

    Returns:
        tuple (delta, percent_change)
        Safely handles None, NaN, Inf, zero baselines without crashing or dividing by zero.
    """
    if baseline is None or comparison is None:
        return None, None

    try:
        b_val = float(baseline)
        c_val = float(comparison)
    except (ValueError, TypeError):
        return None, None

    if math.isnan(b_val) or math.isnan(c_val) or math.isinf(b_val) or math.isinf(c_val):
        return None, None

    delta = round(c_val - b_val, 4)

    if abs(b_val) < 1e-9:
        percent_change = None
    else:
        percent_change = round(((c_val - b_val) / abs(b_val)) * 100.0, 2)

    return delta, percent_change


def classify_direction(
    delta: float | None,
    tolerance: float = 0.1,
) -> str:
    """Classify the direction of a numeric delta relative to a tolerance threshold.

    Allowed values: "increase" | "decrease" | "unchanged" | "insufficient_data"
    """
    if delta is None or math.isnan(delta) or math.isinf(delta):
        return "insufficient_data"

    if delta > tolerance:
        return "increase"
    elif delta < -tolerance:
        return "decrease"
    else:
        return "unchanged"


# ──────────────────────────────────────────────────────────────────────────────
# Metric Extractors & Comparison Definitions
# ──────────────────────────────────────────────────────────────────────────────


def _extract_numeric_metric(record_dict: Mapping[str, Any], keys: list[str]) -> float | None:
    """Extract a numeric metric from a record or its nested metrics dictionary."""
    metrics_dict = record_dict.get("metrics") or record_dict.get("metrics_summary") or {}
    if not isinstance(metrics_dict, Mapping):
        metrics_dict = {}

    for k in keys:
        if k in record_dict and record_dict[k] is not None:
            try:
                v = float(record_dict[k])
                if not (math.isnan(v) or math.isinf(v)):
                    return v
            except (ValueError, TypeError):
                pass
        if k in metrics_dict and metrics_dict[k] is not None:
            try:
                v = float(metrics_dict[k])
                if not (math.isnan(v) or math.isinf(v)):
                    return v
            except (ValueError, TypeError):
                pass
    return None


def build_comparison_metric(
    key: str,
    label: str,
    unit: str,
    baseline_record: Mapping[str, Any],
    comparison_record: Mapping[str, Any],
    candidate_keys: list[str],
    tolerance: float,
    increase_phrase: str,
    decrease_phrase: str,
    unchanged_phrase: str,
) -> ComparisonMetric:
    """Build a deterministic ComparisonMetric from two record mappings."""
    b_val = _extract_numeric_metric(baseline_record, candidate_keys)
    c_val = _extract_numeric_metric(comparison_record, candidate_keys)

    if b_val is None or c_val is None:
        return ComparisonMetric(
            key=key,
            label=label,
            baseline_value=b_val,
            comparison_value=c_val,
            delta=None,
            percent_change=None,
            unit=unit,
            direction="insufficient_data",
            interpretation="Insufficient data for this comparison.",
            evidence=f"Baseline: {b_val if b_val is not None else 'N/A'} | Comparison: {c_val if c_val is not None else 'N/A'}",
            available=False,
        )

    delta, pct_change = calculate_delta(b_val, c_val)
    direction = classify_direction(delta, tolerance=tolerance)

    if direction == "increase":
        interpretation = increase_phrase
    elif direction == "decrease":
        interpretation = decrease_phrase
    else:
        interpretation = unchanged_phrase

    unit_str = f" {unit}" if unit else ""
    delta_str = f"+{delta:.2f}" if delta is not None and delta > 0 else f"{delta:.2f}"
    pct_str = f" ({'+' if pct_change is not None and pct_change > 0 else ''}{pct_change:.1f}%)" if pct_change is not None else ""
    evidence = f"Baseline: {b_val:.2f}{unit_str} → Comparison: {c_val:.2f}{unit_str} (Δ {delta_str}{unit_str}{pct_str})"

    return ComparisonMetric(
        key=key,
        label=label,
        baseline_value=b_val,
        comparison_value=c_val,
        delta=delta,
        percent_change=pct_change,
        unit=unit,
        direction=direction,
        interpretation=interpretation,
        evidence=evidence,
        available=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Comprehensive Record Comparison
# ──────────────────────────────────────────────────────────────────────────────


def compare_analysis_records(
    baseline_record: Any,
    comparison_record: Any,
) -> dict[str, Any]:
    """Perform a pure, deterministic comparison between two completed AnalysisRecord instances.

    Returns structured comparison output containing headline, metrics list,
    changes breakdown, and data quality indicators.
    """
    b_dict = baseline_record.to_dict() if hasattr(baseline_record, "to_dict") else dict(baseline_record)
    c_dict = comparison_record.to_dict() if hasattr(comparison_record, "to_dict") else dict(comparison_record)

    b_id = b_dict.get("analysis_id") or b_dict.get("activity_id") or "Baseline"
    c_id = c_dict.get("analysis_id") or c_dict.get("activity_id") or "Comparison"
    b_loc = b_dict.get("location_label") or "Baseline Location"
    c_loc = c_dict.get("location_label") or "Comparison Location"
    b_date = str(b_dict.get("date") or "Unknown Date")
    c_date = str(c_dict.get("date") or "Unknown Date")

    temp_tol = DECISION_THRESHOLDS["temperature_tolerance_deg_c"]
    spread_tol = DECISION_THRESHOLDS["temperature_spread_tolerance_deg_c"]
    tile_tol = DECISION_THRESHOLDS["tile_count_tolerance"]
    prop_tol = DECISION_THRESHOLDS["proportion_tolerance"]

    metrics: list[ComparisonMetric] = [
        # Mean Temperature
        build_comparison_metric(
            key="mean_temperature",
            label="Mean Temperature",
            unit="°C",
            baseline_record=b_dict,
            comparison_record=c_dict,
            candidate_keys=["mean_temp", "mean_temperature", "observed_temperature", "temperature"],
            tolerance=temp_tol,
            increase_phrase="Warmer conditions observed in Comparison.",
            decrease_phrase="Cooler conditions observed in Comparison.",
            unchanged_phrase="Mean temperature remained consistent within tolerance.",
        ),
        # Min Temperature
        build_comparison_metric(
            key="min_temperature",
            label="Minimum Temperature",
            unit="°C",
            baseline_record=b_dict,
            comparison_record=c_dict,
            candidate_keys=["min_temp", "min_temperature"],
            tolerance=temp_tol,
            increase_phrase="Higher thermal minimum observed in Comparison.",
            decrease_phrase="Lower thermal minimum observed in Comparison.",
            unchanged_phrase="Thermal minimum remained consistent.",
        ),
        # Max Temperature
        build_comparison_metric(
            key="max_temperature",
            label="Maximum Temperature",
            unit="°C",
            baseline_record=b_dict,
            comparison_record=c_dict,
            candidate_keys=["max_temp", "max_temperature"],
            tolerance=temp_tol,
            increase_phrase="Higher thermal maximum observed in Comparison.",
            decrease_phrase="Lower thermal maximum observed in Comparison.",
            unchanged_phrase="Thermal maximum remained consistent.",
        ),
        # Temperature Spread
        build_comparison_metric(
            key="temperature_spread",
            label="Temperature Spread",
            unit="°C",
            baseline_record=b_dict,
            comparison_record=c_dict,
            candidate_keys=["temp_spread", "temperature_spread", "spread"],
            tolerance=spread_tol,
            increase_phrase="Wider thermal range / variability observed in Comparison.",
            decrease_phrase="Narrower thermal range / variability observed in Comparison.",
            unchanged_phrase="Temperature spread remained consistent.",
        ),
        # Spatial Tile Count
        build_comparison_metric(
            key="tile_count",
            label="Analyzed Tiles",
            unit="tiles",
            baseline_record=b_dict,
            comparison_record=c_dict,
            candidate_keys=["total_tiles", "tile_count"],
            tolerance=tile_tol,
            increase_phrase="Greater spatial coverage / tile resolution in Comparison.",
            decrease_phrase="Reduced spatial coverage in Comparison.",
            unchanged_phrase="Spatial tile coverage is identical.",
        ),
        # Above Threshold Proportion
        build_comparison_metric(
            key="above_threshold_proportion",
            label="Above Threshold Proportion",
            unit="%",
            baseline_record=b_dict,
            comparison_record=c_dict,
            candidate_keys=["above_threshold_proportion", "hot_tile_pct"],
            tolerance=prop_tol,
            increase_phrase="Larger proportion of surface area above thermal threshold.",
            decrease_phrase="Smaller proportion of surface area above thermal threshold.",
            unchanged_phrase="Proportion above threshold remained consistent.",
        ),
    ]

    available_metrics = [m for m in metrics if m.available]
    comparable_count = len(available_metrics)
    total_candidate_count = len(metrics)

    increased = [m for m in available_metrics if m.direction == "increase"]
    decreased = [m for m in available_metrics if m.direction == "decrease"]
    unchanged = [m for m in available_metrics if m.direction == "unchanged"]
    missing = [m for m in metrics if not m.available]

    # Deterministic Headline Generation
    mean_temp_metric = next((m for m in metrics if m.key == "mean_temperature"), None)
    if mean_temp_metric and mean_temp_metric.available and mean_temp_metric.delta is not None:
        if mean_temp_metric.direction == "increase":
            headline = f"Warmer conditions observed in Comparison ({'+' if mean_temp_metric.delta > 0 else ''}{mean_temp_metric.delta:.1f}°C)."
        elif mean_temp_metric.direction == "decrease":
            headline = f"Cooler conditions observed in Comparison ({mean_temp_metric.delta:.1f}°C)."
        else:
            headline = "Mean temperature conditions remained consistent between analyses."
    elif comparable_count > 0:
        headline = f"Comparison completed with {comparable_count} comparable metrics."
    else:
        headline = "Insufficient common data points to establish a comparative delta."

    return {
        "baseline_id": b_id,
        "comparison_id": c_id,
        "baseline_location": b_loc,
        "comparison_location": c_loc,
        "baseline_date": b_date,
        "comparison_date": c_date,
        "headline": headline,
        "metrics": metrics,
        "available_metrics": available_metrics,
        "increased": increased,
        "decreased": decreased,
        "unchanged": unchanged,
        "missing": missing,
        "data_quality": {
            "metrics_available": comparable_count,
            "metrics_total": total_candidate_count,
            "metrics_comparable_ratio": f"{comparable_count} / {total_candidate_count}",
            "missing_count": len(missing),
        },
        "disclaimer": RESPONSIBLE_ANALYTICS_DISCLAIMER,
    }
