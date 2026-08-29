"""Deterministic Operational Signal Detection Engine.

Transforms completed AnalysisRecords into explainable operational signals.

Strict Invariants:
1. Zero HTTP / Network I/O — operates purely on in-memory completed AnalysisRecord data.
2. Pure, deterministic mathematical evaluation.
3. Strict non-causal language — no predictions, no causation, no medical risk claims.
4. Transparent data quality indicators on every signal.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import math
from typing import Any, Mapping, Sequence

VALID_SEVERITIES: frozenset[str] = frozenset({"INFO", "WATCH", "ELEVATED", "CRITICAL"})
VALID_DATA_QUALITIES: frozenset[str] = frozenset({"HIGH", "MEDIUM", "LOW", "INSUFFICIENT"})

SEVERITY_WEIGHTS: dict[str, int] = {
    "CRITICAL": 40,
    "ELEVATED": 30,
    "WATCH": 20,
    "INFO": 10,
}


@dataclass(frozen=True)
class OperationalSignal:
    """Immutable representation of an operational intelligence signal."""

    signal_id: str
    analysis_id: str
    signal_type: str
    severity: str  # "INFO" | "WATCH" | "ELEVATED" | "CRITICAL"
    title: str
    description: str
    metric: str | None = None
    observed_value: float | None = None
    threshold_value: float | None = None
    direction: str | None = None  # "above" | "below" | "increase" | "decrease" | "stable"
    confidence: str = "HIGH"  # "HIGH" | "MEDIUM" | "LOW"
    evidence: list[str] = field(default_factory=list)
    data_quality: str = "HIGH"  # "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OperationalSignal:
        return cls(
            signal_id=str(data.get("signal_id", "")),
            analysis_id=str(data.get("analysis_id", "")),
            signal_type=str(data.get("signal_type", "")),
            severity=str(data.get("severity", "INFO")).upper(),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            metric=data.get("metric"),
            observed_value=_safe_float(data.get("observed_value")),
            threshold_value=_safe_float(data.get("threshold_value")),
            direction=data.get("direction"),
            confidence=str(data.get("confidence", "HIGH")),
            evidence=list(data.get("evidence", [])),
            data_quality=str(data.get("data_quality", "HIGH")),
            created_at=str(data.get("created_at", datetime.now().isoformat())),
        )


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _extract_metric_val(record_dict: Mapping[str, Any], candidate_keys: list[str]) -> float | None:
    metrics = record_dict.get("metrics") or record_dict.get("metrics_summary") or {}
    if not isinstance(metrics, Mapping):
        metrics = {}

    for k in candidate_keys:
        if k in record_dict and record_dict[k] is not None:
            v = _safe_float(record_dict[k])
            if v is not None:
                return v
        if k in metrics and metrics[k] is not None:
            v = _safe_float(metrics[k])
            if v is not None:
                return v
    return None


def _determine_record_data_quality(record_dict: Mapping[str, Any]) -> str:
    """Classify the data quality of an AnalysisRecord deterministically."""
    metrics = record_dict.get("metrics") or record_dict.get("metrics_summary") or {}
    if not isinstance(metrics, Mapping):
        metrics = {}

    has_mean = _extract_metric_val(record_dict, ["mean_temp", "mean_temperature", "observed_temperature", "temperature"]) is not None
    has_min = _extract_metric_val(record_dict, ["min_temp", "min_temperature"]) is not None
    has_max = _extract_metric_val(record_dict, ["max_temp", "max_temperature"]) is not None
    has_tiles = _extract_metric_val(record_dict, ["total_tiles", "tile_count"]) is not None

    available_count = sum([has_mean, has_min, has_max, has_tiles])
    if available_count >= 4:
        return "HIGH"
    elif available_count >= 2:
        return "MEDIUM"
    elif available_count == 1:
        return "LOW"
    return "INSUFFICIENT"


# ──────────────────────────────────────────────────────────────────────────────
# Individual Signal Detectors
# ──────────────────────────────────────────────────────────────────────────────


def detect_temperature_threshold_signals(
    record: Any,
    threshold_critical_high: float = 40.0,
    threshold_elevated_high: float = 35.0,
    threshold_watch_high: float = 32.0,
    threshold_low: float = 10.0,
) -> list[OperationalSignal]:
    """Detect temperature threshold exceedance signals."""
    r_dict = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    aid = str(r_dict.get("analysis_id") or r_dict.get("activity_id") or "UNKNOWN")
    loc = str(r_dict.get("location_label") or "Analysis Area")
    date_str = str(r_dict.get("date") or "Unknown Date")
    created = str(r_dict.get("created_at") or datetime.now().isoformat())
    dq = _determine_record_data_quality(r_dict)

    mean_temp = _extract_metric_val(r_dict, ["mean_temp", "mean_temperature", "observed_temperature", "temperature"])
    max_temp = _extract_metric_val(r_dict, ["max_temp", "max_temperature"])

    signals: list[OperationalSignal] = []

    # Determine appropriate trigger metric name
    is_hi_point = r_dict.get("observed_temperature") is not None and not (
        isinstance(r_dict.get("metrics"), Mapping) and r_dict["metrics"].get("mean_temp")
    )
    metric_name = "observed_temperature" if is_hi_point else ("mean_temperature" if mean_temp is not None else "max_temperature")

    # High temperature detection on mean or max
    eval_temp = mean_temp if mean_temp is not None else max_temp
    if eval_temp is not None:
        if eval_temp >= threshold_critical_high:
            signals.append(
                OperationalSignal(
                    signal_id=f"SIG-TH-CRIT-{aid}",
                    analysis_id=aid,
                    signal_type="temperature_above_threshold",
                    severity="CRITICAL",
                    title=f"Critical Thermal Threshold Exceeded ({loc})",
                    description=f"Observed temperature of {eval_temp:.1f}°C meets or exceeds the critical threshold of {threshold_critical_high:.1f}°C.",
                    metric=metric_name,
                    observed_value=eval_temp,
                    threshold_value=threshold_critical_high,
                    direction="above",
                    confidence="HIGH" if dq in ("HIGH", "MEDIUM") else "LOW",
                    evidence=[
                        f"Location: {loc} ({aid})",
                        f"Observed value: {eval_temp:.2f}°C",
                        f"Critical threshold: {threshold_critical_high:.2f}°C",
                        f"Difference: +{eval_temp - threshold_critical_high:.2f}°C",
                        f"Record Date: {date_str}",
                    ],
                    data_quality=dq,
                    created_at=created,
                )
            )
        elif eval_temp >= threshold_elevated_high:
            signals.append(
                OperationalSignal(
                    signal_id=f"SIG-TH-ELEV-{aid}",
                    analysis_id=aid,
                    signal_type="temperature_above_threshold",
                    severity="ELEVATED",
                    title=f"Elevated Temperature Threshold Reached ({loc})",
                    description=f"Observed temperature of {eval_temp:.1f}°C meets or exceeds the elevated threshold of {threshold_elevated_high:.1f}°C.",
                    metric=metric_name,
                    observed_value=eval_temp,
                    threshold_value=threshold_elevated_high,
                    direction="above",
                    confidence="HIGH" if dq in ("HIGH", "MEDIUM") else "MEDIUM",
                    evidence=[
                        f"Location: {loc} ({aid})",
                        f"Observed value: {eval_temp:.2f}°C",
                        f"Elevated threshold: {threshold_elevated_high:.2f}°C",
                        f"Difference: +{eval_temp - threshold_elevated_high:.2f}°C",
                    ],
                    data_quality=dq,
                    created_at=created,
                )
            )
        elif eval_temp >= threshold_watch_high:
            signals.append(
                OperationalSignal(
                    signal_id=f"SIG-TH-WATCH-{aid}",
                    analysis_id=aid,
                    signal_type="temperature_above_threshold",
                    severity="WATCH",
                    title=f"Watch Temperature Threshold Reached ({loc})",
                    description=f"Observed temperature of {eval_temp:.1f}°C meets or exceeds the watch threshold of {threshold_watch_high:.1f}°C.",
                    metric=metric_name,
                    observed_value=eval_temp,
                    threshold_value=threshold_watch_high,
                    direction="above",
                    confidence="HIGH",
                    evidence=[
                        f"Location: {loc} ({aid})",
                        f"Observed value: {eval_temp:.2f}°C",
                        f"Watch threshold: {threshold_watch_high:.2f}°C",
                    ],
                    data_quality=dq,
                    created_at=created,
                )
            )
        elif eval_temp <= threshold_low:
            signals.append(
                OperationalSignal(
                    signal_id=f"SIG-TH-LOW-{aid}",
                    analysis_id=aid,
                    signal_type="temperature_below_threshold",
                    severity="WATCH",
                    title=f"Low Temperature Threshold Observed ({loc})",
                    description=f"Observed temperature of {eval_temp:.1f}°C is at or below the low threshold of {threshold_low:.1f}°C.",
                    metric=metric_name,
                    observed_value=eval_temp,
                    threshold_value=threshold_low,
                    direction="below",
                    confidence="HIGH",
                    evidence=[
                        f"Location: {loc} ({aid})",
                        f"Observed value: {eval_temp:.2f}°C",
                        f"Low threshold: {threshold_low:.2f}°C",
                    ],
                    data_quality=dq,
                    created_at=created,
                )
            )

    return signals


def detect_spatial_spread_signals(
    record: Any,
    high_spread_threshold: float = 8.0,
    low_spread_threshold: float = 1.5,
) -> list[OperationalSignal]:
    """Detect high or low spatial thermal spread signals."""
    r_dict = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    aid = str(r_dict.get("analysis_id") or r_dict.get("activity_id") or "UNKNOWN")
    loc = str(r_dict.get("location_label") or "Analysis Area")
    created = str(r_dict.get("created_at") or datetime.now().isoformat())
    dq = _determine_record_data_quality(r_dict)

    spread = _extract_metric_val(r_dict, ["temp_spread", "temperature_spread", "spread"])
    if spread is None:
        return []

    signals: list[OperationalSignal] = []

    if spread >= high_spread_threshold:
        signals.append(
            OperationalSignal(
                signal_id=f"SIG-SPREAD-HIGH-{aid}",
                analysis_id=aid,
                signal_type="high_spatial_spread",
                severity="ELEVATED",
                title=f"High Thermal Variability ({loc})",
                description=f"Observed spatial temperature spread of {spread:.1f}°C exceeds threshold of {high_spread_threshold:.1f}°C, indicating significant intra-area temperature differences.",
                metric="temperature_spread",
                observed_value=spread,
                threshold_value=high_spread_threshold,
                direction="above",
                confidence="HIGH" if dq == "HIGH" else "MEDIUM",
                evidence=[
                    f"Location: {loc} ({aid})",
                    f"Observed spread: {spread:.2f}°C",
                    f"Threshold: {high_spread_threshold:.2f}°C",
                ],
                data_quality=dq,
                created_at=created,
            )
        )
    elif spread <= low_spread_threshold:
        signals.append(
            OperationalSignal(
                signal_id=f"SIG-SPREAD-LOW-{aid}",
                analysis_id=aid,
                signal_type="low_spatial_spread",
                severity="INFO",
                title=f"Uniform Spatial Temperatures ({loc})",
                description=f"Observed spatial temperature spread of {spread:.1f}°C is within {low_spread_threshold:.1f}°C, indicating homogeneous thermal conditions.",
                metric="temperature_spread",
                observed_value=spread,
                threshold_value=low_spread_threshold,
                direction="below",
                confidence="HIGH",
                evidence=[
                    f"Location: {loc} ({aid})",
                    f"Observed spread: {spread:.2f}°C",
                ],
                data_quality=dq,
                created_at=created,
            )
        )

    return signals


def detect_hot_area_proportion_signals(
    record: Any,
    high_proportion_threshold: float = 0.40,
) -> list[OperationalSignal]:
    """Detect high above-threshold hot area proportion signals."""
    r_dict = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    aid = str(r_dict.get("analysis_id") or r_dict.get("activity_id") or "UNKNOWN")
    loc = str(r_dict.get("location_label") or "Analysis Area")
    created = str(r_dict.get("created_at") or datetime.now().isoformat())
    dq = _determine_record_data_quality(r_dict)

    prop = _extract_metric_val(r_dict, ["above_threshold_proportion", "hot_tile_pct"])
    if prop is None:
        return []

    # Normalize proportion if represented as 0-100 percentage
    norm_prop = prop / 100.0 if prop > 1.0 else prop

    if norm_prop >= high_proportion_threshold:
        pct_display = norm_prop * 100.0
        thresh_display = high_proportion_threshold * 100.0
        return [
            OperationalSignal(
                signal_id=f"SIG-PROP-HIGH-{aid}",
                analysis_id=aid,
                signal_type="high_hot_area_proportion",
                severity="ELEVATED",
                title=f"Significant Surface Proportion Above Threshold ({loc})",
                description=f"{pct_display:.1f}% of evaluated tiles exceed configured thermal thresholds (threshold: {thresh_display:.1f}%).",
                metric="above_threshold_proportion",
                observed_value=pct_display,
                threshold_value=thresh_display,
                direction="above",
                confidence="HIGH" if dq in ("HIGH", "MEDIUM") else "LOW",
                evidence=[
                    f"Location: {loc} ({aid})",
                    f"Above-threshold proportion: {pct_display:.1f}%",
                    f"Threshold: {thresh_display:.1f}%",
                ],
                data_quality=dq,
                created_at=created,
            )
        ]
    return []


def detect_data_quality_signals(record: Any) -> list[OperationalSignal]:
    """Detect data quality or missing metric signals."""
    r_dict = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    aid = str(r_dict.get("analysis_id") or r_dict.get("activity_id") or "UNKNOWN")
    loc = str(r_dict.get("location_label") or "Analysis Area")
    created = str(r_dict.get("created_at") or datetime.now().isoformat())
    dq = _determine_record_data_quality(r_dict)

    signals: list[OperationalSignal] = []

    if dq == "INSUFFICIENT":
        signals.append(
            OperationalSignal(
                signal_id=f"SIG-DQ-INSUF-{aid}",
                analysis_id=aid,
                signal_type="insufficient_data",
                severity="WATCH",
                title=f"Insufficient Metrics for Analysis ({loc})",
                description="Analysis record does not contain sufficient core temperature metrics to compute full operational indicators.",
                metric=None,
                confidence="LOW",
                evidence=[f"Analysis ID: {aid}", "Zero confirmed numeric temperature metrics found."],
                data_quality="INSUFFICIENT",
                created_at=created,
            )
        )
    elif dq == "LOW":
        signals.append(
            OperationalSignal(
                signal_id=f"SIG-DQ-MISSING-{aid}",
                analysis_id=aid,
                signal_type="missing_metric",
                severity="INFO",
                title=f"Partial Metric Coverage ({loc})",
                description="Analysis record contains only limited metrics; secondary spatial indicators were omitted.",
                metric=None,
                confidence="MEDIUM",
                evidence=[f"Analysis ID: {aid}", "Only primary observation point available."],
                data_quality="LOW",
                created_at=created,
            )
        )

    return signals


def detect_temporal_signals(
    records_for_location: Sequence[Any],
    tolerance: float = 0.5,
) -> list[OperationalSignal]:
    """Detect temporal movement, persistence, or stability across a chronological sequence for one location."""
    completed = [
        r for r in records_for_location
        if (getattr(r, "status", None) == "Completed" or (isinstance(r, dict) and r.get("status") == "Completed"))
    ]

    if len(completed) < 2:
        return []

    # Sort chronologically
    def _get_sort_tuple(r: Any) -> tuple[str, str]:
        d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        return str(d.get("date") or "1970-01-01"), str(d.get("time") or "00:00")

    sorted_recs = sorted(completed, key=_get_sort_tuple)
    first_r = sorted_recs[0].to_dict() if hasattr(sorted_recs[0], "to_dict") else dict(sorted_recs[0])
    latest_r = sorted_recs[-1].to_dict() if hasattr(sorted_recs[-1], "to_dict") else dict(sorted_recs[-1])

    first_val = _extract_metric_val(first_r, ["mean_temp", "mean_temperature", "observed_temperature"])
    latest_val = _extract_metric_val(latest_r, ["mean_temp", "mean_temperature", "observed_temperature"])

    if first_val is None or latest_val is None:
        return []

    aid_latest = str(latest_r.get("analysis_id") or latest_r.get("activity_id") or "LATEST")
    loc = str(latest_r.get("location_label") or "Analysis Area")
    created = str(latest_r.get("created_at") or datetime.now().isoformat())
    dq = _determine_record_data_quality(latest_r)

    delta = round(latest_val - first_val, 2)
    signals: list[OperationalSignal] = []

    # Movement detection
    if delta > tolerance:
        sev = "ELEVATED" if delta >= 3.0 else "WATCH"
        signals.append(
            OperationalSignal(
                signal_id=f"SIG-TEMP-INC-{aid_latest}",
                analysis_id=aid_latest,
                signal_type="temperature_increase",
                severity=sev,
                title=f"Observed Temperature Increase ({loc})",
                description=f"Mean temperature rose from {first_val:.1f}°C to {latest_val:.1f}°C (+{delta:.1f}°C) over the observation timeline.",
                metric="mean_temperature",
                observed_value=latest_val,
                threshold_value=first_val,
                direction="increase",
                confidence="HIGH" if len(sorted_recs) >= 3 else "MEDIUM",
                evidence=[
                    f"Initial: {first_val:.2f}°C ({first_r.get('date')})",
                    f"Latest: {latest_val:.2f}°C ({latest_r.get('date')})",
                    f"Net Delta: +{delta:.2f}°C",
                    f"Observations count: {len(sorted_recs)}",
                ],
                data_quality=dq,
                created_at=created,
            )
        )
    elif delta < -tolerance:
        signals.append(
            OperationalSignal(
                signal_id=f"SIG-TEMP-DEC-{aid_latest}",
                analysis_id=aid_latest,
                signal_type="temperature_decrease",
                severity="INFO",
                title=f"Observed Temperature Decline ({loc})",
                description=f"Mean temperature decreased from {first_val:.1f}°C to {latest_val:.1f}°C ({delta:.1f}°C) over the observation timeline.",
                metric="mean_temperature",
                observed_value=latest_val,
                threshold_value=first_val,
                direction="decrease",
                confidence="HIGH" if len(sorted_recs) >= 3 else "MEDIUM",
                evidence=[
                    f"Initial: {first_val:.2f}°C ({first_r.get('date')})",
                    f"Latest: {latest_val:.2f}°C ({latest_r.get('date')})",
                    f"Net Delta: {delta:.2f}°C",
                ],
                data_quality=dq,
                created_at=created,
            )
        )
    else:
        if len(sorted_recs) >= 3:
            signals.append(
                OperationalSignal(
                    signal_id=f"SIG-TEMP-STABLE-{aid_latest}",
                    analysis_id=aid_latest,
                    signal_type="persistent_stability",
                    severity="INFO",
                    title=f"Thermal Stability ({loc})",
                    description=f"Observed temperatures remained stable within ±{tolerance}°C across {len(sorted_recs)} historical observations.",
                    metric="mean_temperature",
                    observed_value=latest_val,
                    threshold_value=first_val,
                    direction="stable",
                    confidence="HIGH",
                    evidence=[
                        f"Span: {first_val:.2f}°C → {latest_val:.2f}°C",
                        f"Net Delta: {delta:.2f}°C",
                        f"Total records evaluated: {len(sorted_recs)}",
                    ],
                    data_quality=dq,
                    created_at=created,
                )
            )

    return signals


# ──────────────────────────────────────────────────────────────────────────────
# Comprehensive Signal Generator
# ──────────────────────────────────────────────────────────────────────────────


def generate_operational_signals(
    records: Sequence[Any],
    *,
    critical_threshold: float = 40.0,
    elevated_threshold: float = 35.0,
    watch_threshold: float = 32.0,
    low_threshold: float = 10.0,
    high_spread_threshold: float = 8.0,
    high_proportion_threshold: float = 0.40,
) -> list[OperationalSignal]:
    """Generate all operational signals across all completed session records with deterministic ordering."""
    completed = [
        r for r in records
        if (getattr(r, "status", None) == "Completed" or (isinstance(r, dict) and r.get("status") == "Completed"))
    ]

    all_signals: list[OperationalSignal] = []

    # Per-record detectors
    for r in completed:
        all_signals.extend(
            detect_temperature_threshold_signals(
                r,
                threshold_critical_high=critical_threshold,
                threshold_elevated_high=elevated_threshold,
                threshold_watch_high=watch_threshold,
                threshold_low=low_threshold,
            )
        )
        all_signals.extend(
            detect_spatial_spread_signals(
                r,
                high_spread_threshold=high_spread_threshold,
            )
        )
        all_signals.extend(
            detect_hot_area_proportion_signals(
                r,
                high_proportion_threshold=high_proportion_threshold,
            )
        )
        all_signals.extend(detect_data_quality_signals(r))

    # Location grouped temporal detectors
    by_loc: dict[str, list[Any]] = {}
    for r in completed:
        d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        loc = str(d.get("location_label") or "Default").lower().strip()
        by_loc.setdefault(loc, []).append(r)

    for loc, loc_records in by_loc.items():
        if len(loc_records) >= 2:
            all_signals.extend(detect_temporal_signals(loc_records))

    # Deterministic sorting: Severity weight descending, created_at descending, signal_id ascending
    def _sort_key(s: OperationalSignal) -> tuple[int, str, str]:
        w = SEVERITY_WEIGHTS.get(s.severity, 0)
        return (-w, s.created_at or "", s.signal_id)

    all_signals.sort(key=_sort_key)
    return all_signals
