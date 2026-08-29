"""Latest vs Previous Change Detection Engine (Phase 17).

Deterministic comparison of the most recent analysis against its predecessor.
Handles edge cases: first analysis, missing metrics, zero baselines, NaN, Inf, negatives.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class MetricChange:
    """Single metric change between baseline and latest."""
    metric_name: str
    baseline_value: float | None
    latest_value: float | None
    difference: float | None
    percentage_change: float | None
    direction: str  # "increased", "decreased", "unchanged", "unavailable"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LatestChangeSummary:
    """Immutable change summary between two comparable analyses."""

    baseline_analysis_id: str | None
    latest_analysis_id: str | None
    is_first_analysis: bool
    changed_metrics: list[MetricChange]
    unchanged_metrics: list[MetricChange]
    newly_triggered_conditions: list[str]
    cleared_conditions: list[str]
    data_quality_change: str | None  # "improved", "degraded", "unchanged", None
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_analysis_id": self.baseline_analysis_id,
            "latest_analysis_id": self.latest_analysis_id,
            "is_first_analysis": self.is_first_analysis,
            "changed_metrics": [m.to_dict() for m in self.changed_metrics],
            "unchanged_metrics": [m.to_dict() for m in self.unchanged_metrics],
            "newly_triggered_conditions": self.newly_triggered_conditions,
            "cleared_conditions": self.cleared_conditions,
            "data_quality_change": self.data_quality_change,
            "limitations": self.limitations,
        }


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _get_record_dict(r: Any) -> dict[str, Any]:
    if hasattr(r, "to_dict"):
        return dict(r.to_dict())
    if isinstance(r, Mapping):
        return dict(r)
    return {}


DQ_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "INSUFFICIENT": 0}

COMPARISON_METRICS = [
    ("observed_temperature", "Observed Temperature"),
    ("mean_temp", "Mean Temperature"),
    ("max_temp", "Maximum Temperature"),
    ("min_temp", "Minimum Temperature"),
    ("temp_spread", "Temperature Spread"),
    ("hot_spot_count", "Hot Spot Count"),
    ("total_tiles", "Total Tiles"),
]


def _percentage_change(baseline: float, latest: float) -> float | None:
    if baseline == 0.0:
        if latest == 0.0:
            return 0.0
        return None  # Cannot compute % change from zero baseline
    return ((latest - baseline) / abs(baseline)) * 100.0


def _compute_metric_change(name: str, baseline_val: float | None, latest_val: float | None) -> MetricChange:
    if baseline_val is None or latest_val is None:
        return MetricChange(
            metric_name=name,
            baseline_value=baseline_val,
            latest_value=latest_val,
            difference=None,
            percentage_change=None,
            direction="unavailable",
        )

    diff = latest_val - baseline_val
    pct = _percentage_change(baseline_val, latest_val)

    if abs(diff) < 1e-9:
        direction = "unchanged"
    elif diff > 0:
        direction = "increased"
    else:
        direction = "decreased"

    return MetricChange(
        metric_name=name,
        baseline_value=baseline_val,
        latest_value=latest_val,
        difference=round(diff, 4),
        percentage_change=round(pct, 2) if pct is not None else None,
        direction=direction,
    )


def _extract_metric(rd: dict, metric_key: str) -> float | None:
    direct = _safe_float(rd.get(metric_key))
    if direct is not None:
        return direct
    metrics = rd.get("metrics", {})
    if isinstance(metrics, dict):
        return _safe_float(metrics.get(metric_key))
    return None


def _extract_dq(rd: dict) -> str:
    dq = rd.get("data_quality")
    if dq and isinstance(dq, str):
        return dq.upper()
    return "HIGH"


def _get_conditions(rd: dict, signals: list[dict] | None = None) -> set[str]:
    """Extract triggered conditions from a record or its signals."""
    conditions: set[str] = set()
    # Check if threshold was exceeded
    metrics = rd.get("metrics", {}) if isinstance(rd.get("metrics"), dict) else {}
    temp = _safe_float(rd.get("observed_temperature")) or _safe_float(metrics.get("mean_temp"))
    threshold = _safe_float(rd.get("threshold")) or _safe_float(metrics.get("threshold"))
    if temp is not None and threshold is not None and temp > threshold:
        conditions.add("threshold_exceeded")

    dq = _extract_dq(rd)
    if dq in ("LOW", "INSUFFICIENT"):
        conditions.add("low_data_quality")

    if signals:
        for sig in signals:
            sig_aid = sig.get("analysis_id", "")
            if sig_aid == rd.get("analysis_id"):
                conditions.add(f"signal:{sig.get('signal_type', 'unknown')}")

    return conditions


def compute_latest_change(
    records: Sequence[Any],
    signals: Sequence[Any] | None = None,
) -> LatestChangeSummary:
    """Compute deterministic change summary between latest and previous analysis."""
    rec_list = [_get_record_dict(r) for r in records]
    sig_list = [_get_record_dict(s) for s in (signals or [])]

    # Sort by date to identify latest and baseline
    dated: list[tuple[str, dict]] = []
    for rd in rec_list:
        d = rd.get("date") or (rd.get("created_at", "")[:10] if rd.get("created_at") else "")
        dated.append((d or "", rd))

    dated.sort(key=lambda x: x[0])

    if len(dated) == 0:
        return LatestChangeSummary(
            baseline_analysis_id=None,
            latest_analysis_id=None,
            is_first_analysis=True,
            changed_metrics=[],
            unchanged_metrics=[],
            newly_triggered_conditions=[],
            cleared_conditions=[],
            data_quality_change=None,
            limitations=["No analyses available for comparison."],
        )

    if len(dated) == 1:
        latest_rd = dated[0][1]
        return LatestChangeSummary(
            baseline_analysis_id=None,
            latest_analysis_id=str(latest_rd.get("analysis_id", "UNKNOWN")),
            is_first_analysis=True,
            changed_metrics=[],
            unchanged_metrics=[],
            newly_triggered_conditions=sorted(_get_conditions(latest_rd, sig_list)),
            cleared_conditions=[],
            data_quality_change=None,
            limitations=["First analysis — no previous observation for comparison."],
        )

    baseline_rd = dated[-2][1]
    latest_rd = dated[-1][1]

    changed: list[MetricChange] = []
    unchanged: list[MetricChange] = []

    for metric_key, metric_label in COMPARISON_METRICS:
        bv = _extract_metric(baseline_rd, metric_key)
        lv = _extract_metric(latest_rd, metric_key)
        mc = _compute_metric_change(metric_label, bv, lv)
        if mc.direction in ("increased", "decreased"):
            changed.append(mc)
        elif mc.direction == "unchanged":
            unchanged.append(mc)
        # "unavailable" metrics are skipped from both lists

    # Data quality change
    base_dq = _extract_dq(baseline_rd)
    latest_dq = _extract_dq(latest_rd)
    if DQ_RANK.get(latest_dq, 3) > DQ_RANK.get(base_dq, 3):
        dq_change = "improved"
    elif DQ_RANK.get(latest_dq, 3) < DQ_RANK.get(base_dq, 3):
        dq_change = "degraded"
    elif base_dq == latest_dq:
        dq_change = "unchanged"
    else:
        dq_change = None

    # Conditions
    base_conds = _get_conditions(baseline_rd, sig_list)
    latest_conds = _get_conditions(latest_rd, sig_list)
    newly_triggered = sorted(latest_conds - base_conds)
    cleared = sorted(base_conds - latest_conds)

    limitations = ["Comparison is between two sequential analyses within the current session."]
    if any(m.direction == "unavailable" for m in [_compute_metric_change("", _extract_metric(baseline_rd, k), _extract_metric(latest_rd, k)) for k, _ in COMPARISON_METRICS]):
        limitations.append("Some metrics unavailable in one or both analyses.")

    return LatestChangeSummary(
        baseline_analysis_id=str(baseline_rd.get("analysis_id", "UNKNOWN")),
        latest_analysis_id=str(latest_rd.get("analysis_id", "UNKNOWN")),
        is_first_analysis=False,
        changed_metrics=changed,
        unchanged_metrics=unchanged,
        newly_triggered_conditions=newly_triggered,
        cleared_conditions=cleared,
        data_quality_change=dq_change,
        limitations=limitations,
    )
