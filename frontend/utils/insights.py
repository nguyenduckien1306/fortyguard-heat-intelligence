"""Analytical Insight Engine for FortyGuard Heat Intelligence.

Derives transparent, deterministic, explainable analytical observations from
confirmed FortyGuard API data. Every insight is traceable to actual values
in the result payload.

NON-AUTHORITATIVE RULE:
    Every insight must be reproducible from the supplied input values alone.
    An insight must never imply causation, significance, safety, risk,
    recommendation, prediction, or domain expertise that is not explicitly
    present in the source data.

Variability thresholds and data-quality classifications are UI/analytics
heuristics — NOT scientific standards. They flow exclusively through the
centralized constants and classification functions defined in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


# ──────────────────────────────────────────────────────────────────────────────
# Severity levels — UI classifications, NOT medical or scientific warnings.
# ──────────────────────────────────────────────────────────────────────────────


class InsightSeverity(str, Enum):
    """Visual severity for analytical insights. These are UI labels only."""

    INFO = "INFO"
    POSITIVE = "POSITIVE"
    ATTENTION = "ATTENTION"
    WARNING = "WARNING"


_SEVERITY_ICONS: dict[InsightSeverity, str] = {
    InsightSeverity.INFO: "ℹ️",
    InsightSeverity.POSITIVE: "✅",
    InsightSeverity.ATTENTION: "🔶",
    InsightSeverity.WARNING: "⚠️",
}

_SEVERITY_LABELS: dict[InsightSeverity, str] = {
    InsightSeverity.INFO: "Informational",
    InsightSeverity.POSITIVE: "Positive",
    InsightSeverity.ATTENTION: "Attention",
    InsightSeverity.WARNING: "Data Notice",
}


def insight_severity_to_icon(severity: InsightSeverity) -> str:
    """Return the icon for a severity level."""
    return _SEVERITY_ICONS.get(severity, "ℹ️")


def insight_severity_to_label(severity: InsightSeverity) -> str:
    """Return the human-readable label for a severity level."""
    return _SEVERITY_LABELS.get(severity, "Info")


# ──────────────────────────────────────────────────────────────────────────────
# Insight dataclass
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Insight:
    """A single analytical observation derived from confirmed data.

    Attributes:
        category: Grouping label (e.g. "Variability", "Data Quality").
        title: Short human-readable heading.
        severity: UI-level visual classification.
        summary: Plain-language description of the observation.
        evidence: How this insight was derived (e.g. "Spread = 4.82 °C").
        metric_key: Machine-readable key for the source metric.
        value: The numeric or string value backing the insight.
        unit: Unit of measurement (e.g. "°C", "tiles", "%").
    """

    category: str
    title: str
    severity: InsightSeverity
    summary: str
    evidence: str = ""
    metric_key: str = ""
    value: Any = None
    unit: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Variability thresholds — UI/analytics heuristics, NOT scientific standards.
#
# These thresholds describe spatial temperature spread across analyzed tiles.
# They are descriptive labels for user orientation and do NOT represent
# validated climatological, urban-heat-island, or public-health thresholds.
# ──────────────────────────────────────────────────────────────────────────────

VARIABILITY_THRESHOLDS: list[tuple[float, str, InsightSeverity]] = [
    # (upper_bound_exclusive, label, severity)
    (0.5, "Very Low", InsightSeverity.INFO),
    (2.0, "Low", InsightSeverity.INFO),
    (5.0, "Moderate", InsightSeverity.ATTENTION),
    # Anything >= 5.0 is High
]

_VARIABILITY_HIGH_LABEL = "High"
_VARIABILITY_HIGH_SEVERITY = InsightSeverity.ATTENTION


def classify_temperature_variability(
    spread: float | None,
) -> tuple[str, InsightSeverity]:
    """Classify temperature spread into a descriptive variability label.

    Args:
        spread: max_temperature - min_temperature across valid tiles.

    Returns:
        (label, severity) tuple. Returns ("Insufficient Data", WARNING) if
        spread is None or non-numeric.

    Classification is based on VARIABILITY_THRESHOLDS and nowhere else.
    """
    if spread is None:
        return "Insufficient Data", InsightSeverity.WARNING

    try:
        spread_val = float(spread)
    except (ValueError, TypeError):
        return "Insufficient Data", InsightSeverity.WARNING

    for upper_bound, label, severity in VARIABILITY_THRESHOLDS:
        if spread_val < upper_bound:
            return label, severity

    return _VARIABILITY_HIGH_LABEL, _VARIABILITY_HIGH_SEVERITY


# ──────────────────────────────────────────────────────────────────────────────
# Data quality classification
# ──────────────────────────────────────────────────────────────────────────────


def classify_data_quality(
    total: int | None,
    valid: int | None,
    missing: int | None = None,
) -> tuple[str, InsightSeverity]:
    """Classify structural data completeness.

    Classifications:
        Complete       — all tiles have valid temperature values.
        Mostly Complete — >90% of tiles have valid values.
        Partial        — 50–90% valid.
        Insufficient   — <50% valid or no tiles.

    These describe structural completeness only. They do NOT claim
    accuracy of the source data.
    """
    if total is None or total == 0:
        return "Insufficient", InsightSeverity.WARNING

    if valid is None:
        if missing is not None:
            valid = total - missing
        else:
            return "Insufficient", InsightSeverity.WARNING

    ratio = valid / total if total > 0 else 0.0

    if ratio >= 1.0:
        return "Complete", InsightSeverity.POSITIVE
    elif ratio > 0.9:
        return "Mostly Complete", InsightSeverity.INFO
    elif ratio >= 0.5:
        return "Partial", InsightSeverity.ATTENTION
    else:
        return "Insufficient", InsightSeverity.WARNING


# ──────────────────────────────────────────────────────────────────────────────
# Above-threshold tile proportion
# ──────────────────────────────────────────────────────────────────────────────


def calculate_above_threshold_proportion(
    tile_temperatures: Sequence[float | int],
    threshold: float,
) -> float | None:
    """Calculate the proportion of tiles whose temperature exceeds a threshold.

    Args:
        tile_temperatures: Sequence of numeric temperature values.
            Non-numeric, None, NaN, and infinite values are excluded.
        threshold: The explicit temperature threshold to compare against.

    Returns:
        Proportion as a float in [0.0, 1.0], or None if no valid values exist.

    This reports a simple ratio. It does NOT imply spatial clustering,
    statistical significance, or domain-specific meaning.
    """
    import math

    valid_temps: list[float] = []
    for t in tile_temperatures:
        if t is None:
            continue
        try:
            val = float(t)
            if math.isnan(val) or math.isinf(val):
                continue
            valid_temps.append(val)
        except (ValueError, TypeError):
            continue

    if not valid_temps:
        return None

    above_count = sum(1 for t in valid_temps if t > threshold)
    return above_count / len(valid_temps)


# ──────────────────────────────────────────────────────────────────────────────
# Heatmap insight generation
# ──────────────────────────────────────────────────────────────────────────────


def generate_heatmap_insights(
    tile_metrics: Mapping[str, Any] | None,
    quality_report: Mapping[str, Any] | None = None,
) -> list[Insight]:
    """Generate a list of deterministic analytical insights from Heatmap data.

    Every insight has an explainable basis traceable to actual metric values.
    No causality, significance, or safety claims are made.

    Args:
        tile_metrics: Output of compute_tile_metrics().
        quality_report: Output of get_heatmap_data_quality_report().

    Returns:
        List of Insight objects, ordered by category.
    """
    if not tile_metrics or not isinstance(tile_metrics, Mapping):
        return [
            Insight(
                category="Data",
                title="No Analytical Data",
                severity=InsightSeverity.WARNING,
                summary="No tile metrics are available for analysis.",
            )
        ]

    insights: list[Insight] = []
    total_tiles = tile_metrics.get("total_tiles", 0)
    valid_count = tile_metrics.get("valid_tiles_count", 0)
    missing_count = tile_metrics.get("missing_tiles_count", 0)
    min_temp = tile_metrics.get("min_temp")
    max_temp = tile_metrics.get("max_temp")
    mean_temp = tile_metrics.get("mean_temp")
    spread = tile_metrics.get("temp_spread")
    hottest = tile_metrics.get("hottest_tile")
    coolest = tile_metrics.get("coolest_tile")

    # ── Tile coverage ──
    if total_tiles > 0:
        insights.append(Insight(
            category="Coverage",
            title="Spatial Coverage",
            severity=InsightSeverity.INFO,
            summary=f"{total_tiles} spatial tiles analyzed.",
            evidence=f"total_tiles = {total_tiles}",
            metric_key="total_tiles",
            value=total_tiles,
            unit="tiles",
        ))

    # ── Data completeness ──
    quality_label, quality_sev = classify_data_quality(total_tiles, valid_count, missing_count)

    if total_tiles > 0:
        if missing_count == 0:
            insights.append(Insight(
                category="Data Quality",
                title="Temperature Data Completeness",
                severity=InsightSeverity.POSITIVE,
                summary=f"All {valid_count} tiles contain valid average temperature values.",
                evidence=f"valid = {valid_count}, missing = 0, classification = {quality_label}",
                metric_key="data_quality",
                value=quality_label,
            ))
        elif missing_count > 0:
            pct = round(valid_count / total_tiles * 100, 1) if total_tiles > 0 else 0
            insights.append(Insight(
                category="Data Quality",
                title="Temperature Data Completeness",
                severity=quality_sev,
                summary=f"{valid_count} of {total_tiles} tiles contain valid average temperature values ({pct}%).",
                evidence=f"valid = {valid_count}, missing = {missing_count}, classification = {quality_label}",
                metric_key="data_quality",
                value=quality_label,
            ))

    # ── Temperature variability ──
    if spread is not None:
        var_label, var_sev = classify_temperature_variability(spread)
        insights.append(Insight(
            category="Variability",
            title="Temperature Variability",
            severity=var_sev,
            summary=f"Temperature variability is {var_label.lower()} across the analyzed tiles.",
            evidence=f"Spread = {spread:.2f} °C (max − min), classification = {var_label}",
            metric_key="temp_spread",
            value=spread,
            unit="°C",
        ))

    # ── Mean temperature ──
    if mean_temp is not None:
        insights.append(Insight(
            category="Central Tendency",
            title="Mean Temperature",
            severity=InsightSeverity.INFO,
            summary=f"The mean temperature across valid tiles is {mean_temp:.2f} °C.",
            evidence=f"mean = {mean_temp:.2f} °C over {valid_count} valid tiles",
            metric_key="mean_temp",
            value=mean_temp,
            unit="°C",
        ))

    # ── Hottest tile ──
    if hottest and isinstance(hottest, Mapping):
        tile_id = hottest.get("tile_id", "N/A")
        temp = hottest.get("temperature")
        if temp is not None:
            insights.append(Insight(
                category="Extremes",
                title="Hottest Tile",
                severity=InsightSeverity.INFO,
                summary=f"The hottest tile is Tile {tile_id} at {temp:.2f} °C.",
                evidence=f"tile_id = {tile_id}, temperature = {temp:.2f} °C",
                metric_key="hottest_tile",
                value=temp,
                unit="°C",
            ))

    # ── Coolest tile ──
    if coolest and isinstance(coolest, Mapping):
        tile_id = coolest.get("tile_id", "N/A")
        temp = coolest.get("temperature")
        if temp is not None:
            insights.append(Insight(
                category="Extremes",
                title="Coolest Tile",
                severity=InsightSeverity.INFO,
                summary=f"The coolest tile is Tile {tile_id} at {temp:.2f} °C.",
                evidence=f"tile_id = {tile_id}, temperature = {temp:.2f} °C",
                metric_key="coolest_tile",
                value=temp,
                unit="°C",
            ))

    return insights


# ──────────────────────────────────────────────────────────────────────────────
# Comparison insight generation
# ──────────────────────────────────────────────────────────────────────────────

_COMPARISON_METRIC_INTERPRETATIONS: dict[str, tuple[str, str, str]] = {
    # metric_key: (higher_phrase, lower_phrase, unit_type)
    # unit_type: "temperature" for neutral framing, "count" for tile counts
    "mean_temp": ("Warmer in B", "Cooler in B", "temperature"),
    "min_temp": ("Higher minimum in B", "Lower minimum in B", "temperature"),
    "max_temp": ("Higher maximum in B", "Lower maximum in B", "temperature"),
    "temp_spread": ("Wider range in B", "Narrower range in B", "temperature"),
    "tile_count": ("More tiles in B", "Fewer tiles in B", "count"),
}


def generate_comparison_insights(
    comparison_result: Mapping[str, Any] | None,
) -> list[Insight]:
    """Generate plain-language interpretations from a comparison result.

    Uses neutral descriptive language. Does NOT claim statistical significance,
    causation, or that any direction of change is inherently good or bad.

    Args:
        comparison_result: Output of compare_heatmap_analyses().

    Returns:
        List of Insight objects for comparison deltas.
    """
    if not comparison_result or not comparison_result.get("is_valid"):
        return []

    insights: list[Insight] = []
    label_a = comparison_result.get("analysis_a_label", "A")
    label_b = comparison_result.get("analysis_b_label", "B")

    for metric in comparison_result.get("compared_metrics", []):
        key = metric.get("metric_key", "")
        diff = metric.get("raw_diff")
        diff_fmt = metric.get("diff_formatted", "")

        if diff is None:
            continue

        interp = _COMPARISON_METRIC_INTERPRETATIONS.get(key)
        if not interp:
            continue

        higher_phrase, lower_phrase, _ = interp

        if diff > 0:
            interpretation = higher_phrase
        elif diff < 0:
            interpretation = lower_phrase
        else:
            interpretation = "No difference"

        insights.append(Insight(
            category="Comparison",
            title=metric.get("label", key),
            severity=InsightSeverity.INFO,
            summary=f"{metric.get('label', key)}: {interpretation} ({diff_fmt}).",
            evidence=f"A ({label_a}) = {metric.get('value_a')}, B ({label_b}) = {metric.get('value_b')}, Δ = {diff_fmt}",
            metric_key=key,
            value=diff,
            unit=metric.get("unit", ""),
        ))

    return insights


# ──────────────────────────────────────────────────────────────────────────────
# Summary formatter
# ──────────────────────────────────────────────────────────────────────────────


def format_insight_summary(insights: Sequence[Insight]) -> str:
    """Format a list of insights into a readable text summary.

    Each insight is rendered as:
        [SEVERITY] Title — Summary (Evidence)
    """
    if not insights:
        return "No analytical insights available."

    lines: list[str] = []
    for ins in insights:
        icon = insight_severity_to_icon(ins.severity)
        line = f"{icon} [{ins.severity.value}] {ins.title} — {ins.summary}"
        if ins.evidence:
            line += f" ({ins.evidence})"
        lines.append(line)

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Responsible analytics disclaimer
# ──────────────────────────────────────────────────────────────────────────────

ANALYTICS_DISCLAIMER = (
    "Insights shown here are descriptive calculations derived from the "
    "returned API data; they are not additional FortyGuard classifications. "
    "Variability thresholds and quality classifications are application-level "
    "heuristics and do not represent scientific or regulatory standards."
)
