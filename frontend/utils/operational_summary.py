"""Session-Local Operational Executive Summary Engine (Phase 17).

Provides deterministic operational posture summaries derived exclusively from
completed session analyses, active watchlists, signals, alerts, and investigations
with zero network dependencies and strict non-causal reporting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from frontend.utils.clock import Clock, get_current_clock
from frontend.utils.responsible_analytics import RESPONSIBLE_ANALYTICS_NOTICE


@dataclass(frozen=True)
class OperationalSummary:
    """Immutable structured executive summary of active session state."""

    has_data: bool
    completed_analyses: int
    active_watchlists: int
    triggered_watchlists: int
    active_signals: int
    unresolved_alerts: int
    high_priority_alerts: int
    investigations_open: int
    investigations_in_review: int
    investigations_resolved: int
    latest_analysis_date: str | None
    earliest_analysis_date: str | None
    locations_represented: list[str]
    analysis_types: dict[str, int]
    data_quality_distribution: dict[str, int]
    severity_distribution: dict[str, int]
    generated_at: str
    summary_narrative: str
    disclaimer: str = RESPONSIBLE_ANALYTICS_NOTICE

    def to_dict(self) -> dict[str, Any]:
        """Convert summary to JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OperationalSummary:
        """Construct summary from dictionary representation."""
        return cls(
            has_data=bool(data.get("has_data", False)),
            completed_analyses=int(data.get("completed_analyses", 0)),
            active_watchlists=int(data.get("active_watchlists", 0)),
            triggered_watchlists=int(data.get("triggered_watchlists", 0)),
            active_signals=int(data.get("active_signals", 0)),
            unresolved_alerts=int(data.get("unresolved_alerts", 0)),
            high_priority_alerts=int(data.get("high_priority_alerts", 0)),
            investigations_open=int(data.get("investigations_open", 0)),
            investigations_in_review=int(data.get("investigations_in_review", 0)),
            investigations_resolved=int(data.get("investigations_resolved", 0)),
            latest_analysis_date=str(data["latest_analysis_date"]) if data.get("latest_analysis_date") else None,
            earliest_analysis_date=str(data["earliest_analysis_date"]) if data.get("earliest_analysis_date") else None,
            locations_represented=list(data.get("locations_represented", [])),
            analysis_types=dict(data.get("analysis_types", {})),
            data_quality_distribution=dict(data.get("data_quality_distribution", {})),
            severity_distribution=dict(data.get("severity_distribution", {})),
            generated_at=str(data.get("generated_at", "")),
            summary_narrative=str(data.get("summary_narrative", "")),
            disclaimer=str(data.get("disclaimer", RESPONSIBLE_ANALYTICS_NOTICE)),
        )


def build_operational_summary(
    records: Sequence[Any] | None = None,
    watchlists: Sequence[Any] | None = None,
    watchlist_evaluations: Sequence[Any] | None = None,
    signals: Sequence[Any] | None = None,
    alerts: Sequence[Any] | None = None,
    queue_items: Sequence[Any] | None = None,
    clock: Clock | None = None,
) -> OperationalSummary:
    """Build a deterministic executive operational summary from session components."""
    clk = clock or get_current_clock()
    now_iso = clk.now_iso()

    rec_list = list(records) if records is not None else []
    wl_list = list(watchlists) if watchlists is not None else []
    wl_eval_list = list(watchlist_evaluations) if watchlist_evaluations is not None else []
    sig_list = list(signals) if signals is not None else []
    alert_list = list(alerts) if alerts is not None else []
    q_list = list(queue_items) if queue_items is not None else []

    # 1. Analyses & Dates
    completed_recs = []
    locations_set: set[str] = set()
    dates_list: list[str] = []
    type_counts: dict[str, int] = {"heatmap": 0, "heat_intelligence": 0}
    dq_counts: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "INSUFFICIENT": 0}

    for r in rec_list:
        r_dict = r.to_dict() if hasattr(r, "to_dict") else (dict(r) if isinstance(r, Mapping) else {})
        status = str(r_dict.get("status", "")).title()
        if status in ("Completed", "Success", "Done") or not status:
            completed_recs.append(r_dict)

            # Location
            loc = r_dict.get("location_label") or r_dict.get("location") or r_dict.get("label")
            if loc and isinstance(loc, str) and loc.strip():
                locations_set.add(loc.strip())

            # Date
            d = r_dict.get("date") or (r_dict.get("created_at", "")[:10] if r_dict.get("created_at") else None)
            if d and isinstance(d, str) and len(d) >= 4:
                dates_list.append(d)

            # Analysis Type
            a_type = str(r_dict.get("analysis_type", "heatmap")).lower()
            if "heat_intelligence" in a_type or "point" in a_type:
                type_counts["heat_intelligence"] = type_counts.get("heat_intelligence", 0) + 1
            else:
                type_counts["heatmap"] = type_counts.get("heatmap", 0) + 1

            # Data Quality
            dq = r_dict.get("data_quality")
            if not dq:
                from frontend.utils.operational_intelligence import _determine_record_data_quality
                dq = _determine_record_data_quality(r_dict)
            dq_str = str(dq).upper()
            if dq_str in dq_counts:
                dq_counts[dq_str] += 1
            else:
                dq_counts["INSUFFICIENT"] += 1

    sorted_dates = sorted(dates_list)
    latest_date = sorted_dates[-1] if sorted_dates else None
    earliest_date = sorted_dates[0] if sorted_dates else None
    locations_represented = sorted(list(locations_set))

    # 2. Watchlists
    active_wl_count = len(wl_list)
    matched_wl_count = 0
    for we in wl_eval_list:
        we_dict = we.to_dict() if hasattr(we, "to_dict") else (dict(we) if isinstance(we, Mapping) else {})
        if we_dict.get("matched") or we_dict.get("status") == "TRIGGERED":
            matched_wl_count += 1

    # 3. Signals & Severities
    sev_counts: dict[str, int] = {"CRITICAL": 0, "ELEVATED": 0, "WATCH": 0, "INFO": 0}
    active_sigs = 0
    for s in sig_list:
        s_dict = s.to_dict() if hasattr(s, "to_dict") else (dict(s) if isinstance(s, Mapping) else {})
        disp = str(s_dict.get("disposition", "NEW")).upper()
        if disp not in ("RESOLVED", "DISMISSED"):
            active_sigs += 1
        sev = str(s_dict.get("severity", "INFO")).upper()
        if sev in sev_counts:
            sev_counts[sev] += 1
        elif sev == "HIGH":
            sev_counts["ELEVATED"] += 1
        elif sev == "MEDIUM":
            sev_counts["WATCH"] += 1
        elif sev == "LOW":
            sev_counts["INFO"] += 1

    # 4. Alerts
    unresolved_alerts = 0
    high_priority_alerts = 0
    for a in alert_list:
        a_dict = a.to_dict() if hasattr(a, "to_dict") else (dict(a) if isinstance(a, Mapping) else {})
        status = str(a_dict.get("status", "ACTIVE")).upper()
        if status not in ("RESOLVED", "DISMISSED", "SUPPRESSED", "COOLING_DOWN"):
            unresolved_alerts += 1
            sev = str(a_dict.get("severity", "")).upper()
            pri = str(a_dict.get("priority", "")).upper()
            if sev in ("CRITICAL", "ELEVATED") or pri in ("CRITICAL", "HIGH"):
                high_priority_alerts += 1

    # 5. Investigation Queue
    open_q = 0
    review_q = 0
    resolved_q = 0
    for q in q_list:
        q_dict = q.to_dict() if hasattr(q, "to_dict") else (dict(q) if isinstance(q, Mapping) else {})
        q_stat = str(q_dict.get("status", "OPEN")).upper()
        if q_stat == "OPEN":
            open_q += 1
        elif q_stat in ("IN_REVIEW", "IN REVIEW"):
            review_q += 1
        elif q_stat in ("RESOLVED", "CLOSED"):
            resolved_q += 1

    has_data = len(completed_recs) > 0 or len(sig_list) > 0 or len(q_list) > 0

    # Build Narrative
    if not has_data:
        narrative = "No completed analyses or active operational signals recorded in the current session."
    else:
        narrative_parts = [
            f"Session contains {len(completed_recs)} completed analyses across {len(locations_represented)} location(s)."
        ]
        if unresolved_alerts > 0:
            narrative_parts.append(f"{unresolved_alerts} unresolved alert(s) detected ({high_priority_alerts} high-priority).")
        else:
            narrative_parts.append("Zero active unresolved alerts.")

        if open_q > 0 or review_q > 0:
            narrative_parts.append(f"Investigation queue: {open_q} open, {review_q} under review.")

        if matched_wl_count > 0:
            narrative_parts.append(f"{matched_wl_count} watchlist match(es) triggered.")

        narrative = " ".join(narrative_parts)

    return OperationalSummary(
        has_data=has_data,
        completed_analyses=len(completed_recs),
        active_watchlists=active_wl_count,
        triggered_watchlists=matched_wl_count,
        active_signals=active_sigs,
        unresolved_alerts=unresolved_alerts,
        high_priority_alerts=high_priority_alerts,
        investigations_open=open_q,
        investigations_in_review=review_q,
        investigations_resolved=resolved_q,
        latest_analysis_date=latest_date,
        earliest_analysis_date=earliest_date,
        locations_represented=locations_represented,
        analysis_types=type_counts,
        data_quality_distribution=dq_counts,
        severity_distribution=sev_counts,
        generated_at=now_iso,
        summary_narrative=narrative,
    )
