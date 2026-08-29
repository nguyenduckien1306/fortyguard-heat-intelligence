"""Pure Chronological Investigation Timeline and Longitudinal Trend Engine.

Strict Invariants:
1. Zero network I/O, zero external requests.
2. Only confirmed AnalysisRecord entries with status == 'Completed' participate.
3. Trends are purely descriptive observations, never predictions or forecasts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any, Sequence

from frontend.utils.decision_intelligence import (
    DECISION_THRESHOLDS,
    calculate_delta,
    classify_direction,
)


@dataclass(frozen=True)
class TimelineEvent:
    """Immutable representation of a completed analysis in an investigation timeline."""

    analysis_id: str
    activity_id: str
    date: str
    time: str
    location: str
    analysis_type: str
    mean_temperature: float | None
    min_temperature: float | None
    max_temperature: float | None
    spread: float | None
    tile_count: int | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "activity_id": self.activity_id,
            "date": self.date,
            "time": self.time,
            "location": self.location,
            "analysis_type": self.analysis_type,
            "mean_temperature": self.mean_temperature,
            "min_temperature": self.min_temperature,
            "max_temperature": self.max_temperature,
            "spread": self.spread,
            "tile_count": self.tile_count,
            "status": self.status,
        }


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


def record_to_timeline_event(record: Any) -> TimelineEvent:
    """Convert an AnalysisRecord into an immutable TimelineEvent."""
    r_dict = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    metrics = r_dict.get("metrics") or r_dict.get("metrics_summary") or {}
    if not isinstance(metrics, dict):
        metrics = {}

    mean_t = _safe_float(
        metrics.get("mean_temp")
        or metrics.get("mean_temperature")
        or r_dict.get("observed_temperature")
        or r_dict.get("temperature")
    )
    min_t = _safe_float(metrics.get("min_temp") or metrics.get("min_temperature"))
    max_t = _safe_float(metrics.get("max_temp") or metrics.get("max_temperature"))
    spread = _safe_float(metrics.get("temp_spread") or metrics.get("temperature_spread") or metrics.get("spread"))
    tiles = _safe_int(metrics.get("total_tiles") or metrics.get("tile_count"))

    return TimelineEvent(
        analysis_id=str(r_dict.get("analysis_id") or r_dict.get("activity_id") or ""),
        activity_id=str(r_dict.get("activity_id") or ""),
        date=str(r_dict.get("date") or "Unknown"),
        time=str(r_dict.get("time") or ""),
        location=str(r_dict.get("location_label") or "Unnamed Location"),
        analysis_type=str(r_dict.get("analysis_type") or "heatmap"),
        mean_temperature=mean_t,
        min_temperature=min_t,
        max_temperature=max_t,
        spread=spread,
        tile_count=tiles,
        status=str(r_dict.get("status") or "Completed"),
    )


def build_investigation_timeline(
    records: Sequence[Any],
    *,
    location: str | None = None,
    analysis_type: str | None = None,
    ascending: bool = True,
) -> list[TimelineEvent]:
    """Construct a deduplicated, chronologically ordered timeline from completed records."""
    completed = [
        r for r in records
        if (getattr(r, "status", None) == "Completed" or (isinstance(r, dict) and r.get("status") == "Completed"))
    ]

    events: list[TimelineEvent] = []
    seen_ids: set[str] = set()

    for r in completed:
        event = record_to_timeline_event(r)
        if not event.analysis_id or event.analysis_id in seen_ids:
            continue

        # Location filtering
        if location and location.lower() not in event.location.lower():
            continue

        # Analysis type filtering
        if analysis_type and analysis_type.lower() not in event.analysis_type.lower():
            continue

        seen_ids.add(event.analysis_id)
        events.append(event)

    # Sort key: parse date/time or fallback to string
    def sort_key(ev: TimelineEvent) -> tuple[datetime, str]:
        date_part = ev.date if ev.date and ev.date != "Unknown" else "1970-01-01"
        time_part = ev.time if ev.time else "00:00:00"
        dt_str = f"{date_part} {time_part}".strip()
        try:
            parsed = datetime.fromisoformat(dt_str)
        except ValueError:
            try:
                parsed = datetime.strptime(date_part, "%Y-%m-%d")
            except ValueError:
                parsed = datetime.min
        return parsed, ev.analysis_id

    events.sort(key=sort_key, reverse=not ascending)
    return events


def calculate_timeline_trend(
    events: Sequence[TimelineEvent],
    metric_name: str = "mean_temperature",
) -> dict[str, Any]:
    """Deterministically classify historical trend across chronologically sorted timeline events.

    Trend Classifications:
    - 'Rising': Values consistently increase or net positive change beyond threshold.
    - 'Falling': Values consistently decrease or net negative change beyond threshold.
    - 'Stable': Values remain within tolerance threshold across all observations.
    - 'Mixed': Observations fluctuate in opposing directions across observations.
    - 'Insufficient Data': Fewer than 2 valid numeric observations.
    """
    valid_points = [
        (ev.date, getattr(ev, metric_name))
        for ev in events
        if getattr(ev, metric_name, None) is not None
    ]

    if len(valid_points) < 2:
        return {
            "trend": "Insufficient Data",
            "summary": "At least two completed analyses with valid data are required to evaluate a timeline trend.",
            "observation_count": len(valid_points),
            "first_value": valid_points[0][1] if valid_points else None,
            "last_value": valid_points[-1][1] if valid_points else None,
            "net_delta": None,
            "percent_change": None,
        }

    first_date, first_val = valid_points[0]
    last_date, last_val = valid_points[-1]

    net_delta, pct_change = calculate_delta(first_val, last_val)
    temp_tol = DECISION_THRESHOLDS.get("temperature_tolerance_deg_c", 0.1)

    # Check pair-by-pair increments with rounded deltas to avoid float precision issues
    deltas = [round(valid_points[i + 1][1] - valid_points[i][1], 4) for i in range(len(valid_points) - 1)]
    has_increases = any(d > temp_tol for d in deltas)
    has_decreases = any(d < -temp_tol for d in deltas)

    if has_increases and not has_decreases:
        trend = "Rising"
        summary = f"Observed {metric_name.replace('_', ' ')} increased across all timeline observations ({first_val:.1f} → {last_val:.1f})."
    elif has_decreases and not has_increases:
        trend = "Falling"
        summary = f"Observed {metric_name.replace('_', ' ')} decreased across all timeline observations ({first_val:.1f} → {last_val:.1f})."
    elif not has_increases and not has_decreases:
        trend = "Stable"
        summary = f"Observed {metric_name.replace('_', ' ')} remained stable within ±{temp_tol}°C across timeline observations."
    else:
        # Mixed fluctuations
        net_dir = classify_direction(net_delta, tolerance=temp_tol)
        if net_dir == "increase":
            trend = "Mixed"
            summary = f"Fluctuating values with a net increase from {first_val:.1f} to {last_val:.1f} ({'+' if net_delta and net_delta > 0 else ''}{net_delta:.1f})."
        elif net_dir == "decrease":
            trend = "Mixed"
            summary = f"Fluctuating values with a net decrease from {first_val:.1f} to {last_val:.1f} ({net_delta:.1f})."
        else:
            trend = "Mixed"
            summary = f"Fluctuating values with no net change from start ({first_val:.1f}) to end ({last_val:.1f})."

    return {
        "trend": trend,
        "summary": summary,
        "observation_count": len(valid_points),
        "first_value": first_val,
        "last_value": last_val,
        "first_date": first_date,
        "last_date": last_date,
        "net_delta": net_delta,
        "percent_change": pct_change,
        "observations": valid_points,
    }


def build_multi_analysis_matrix(
    records: Sequence[Any],
    max_analyses: int = 5,
) -> dict[str, Any]:
    """Construct a multi-analysis comparison matrix for up to N completed records."""
    timeline = build_investigation_timeline(records, ascending=True)[:max_analyses]

    if not timeline:
        return {"headers": [], "rows": [], "count": 0}

    headers = [f"{ev.date} ({ev.analysis_id})" for ev in timeline]

    rows = [
        {
            "metric": "Mean Temperature (°C)",
            "values": [f"{ev.mean_temperature:.1f}" if ev.mean_temperature is not None else "—" for ev in timeline],
        },
        {
            "metric": "Min Temperature (°C)",
            "values": [f"{ev.min_temperature:.1f}" if ev.min_temperature is not None else "—" for ev in timeline],
        },
        {
            "metric": "Max Temperature (°C)",
            "values": [f"{ev.max_temperature:.1f}" if ev.max_temperature is not None else "—" for ev in timeline],
        },
        {
            "metric": "Temperature Spread (°C)",
            "values": [f"{ev.spread:.1f}" if ev.spread is not None else "—" for ev in timeline],
        },
        {
            "metric": "Analyzed Tiles",
            "values": [str(ev.tile_count) if ev.tile_count is not None else "—" for ev in timeline],
        },
    ]

    first = timeline[0]
    last = timeline[-1]
    net_temp_delta, _ = calculate_delta(first.mean_temperature, last.mean_temperature)

    return {
        "headers": headers,
        "rows": rows,
        "count": len(timeline),
        "first_analysis_id": first.analysis_id,
        "last_analysis_id": last.analysis_id,
        "net_temperature_delta": net_temp_delta,
    }
