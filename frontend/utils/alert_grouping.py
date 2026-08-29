"""Alert Clustering / Related Alerts Engine (Phase 17).

Groups related alerts by analysis, location, watchlist, signal fingerprint,
criterion, and investigation. Preserves individual alert IDs.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


def _get_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return dict(obj.to_dict())
    if isinstance(obj, Mapping):
        return dict(obj)
    return {}


@dataclass(frozen=True)
class AlertGroup:
    """Immutable grouping of related alerts."""

    group_id: str
    group_title: str
    grouping_key: str
    grouping_value: str
    member_alert_ids: list[str]
    dominant_severity: str
    highest_priority: float
    evidence_count: int
    investigation_state: str  # "none", "open", "in_review", "resolved"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SEVERITY_RANK = {"CRITICAL": 4, "ELEVATED": 3, "WATCH": 2, "INFO": 1}


def _dominant_severity(alerts: list[dict]) -> str:
    best = "INFO"
    best_rank = 0
    for a in alerts:
        sev = str(a.get("severity", "INFO")).upper()
        rank = SEVERITY_RANK.get(sev, 0)
        if rank > best_rank:
            best = sev
            best_rank = rank
    return best


def _highest_priority(alerts: list[dict]) -> float:
    best = 0.0
    for a in alerts:
        try:
            p = float(a.get("priority_score", a.get("priority", 0)))
        except (TypeError, ValueError):
            p = 0.0
        if p > best:
            best = p
    return best


def _make_group_id(key: str, value: str) -> str:
    raw = f"{key}:{value}"
    return f"AG-{hashlib.sha256(raw.encode()).hexdigest()[:12].upper()}"


def _investigation_state_for_group(group_alerts: list[dict], queue_items: list[dict]) -> str:
    """Determine aggregate investigation state for a group of alerts."""
    alert_ids = {str(a.get("alert_id", "")) for a in group_alerts if a.get("alert_id")}
    analysis_ids = {str(a.get("analysis_id", "")) for a in group_alerts if a.get("analysis_id")}
    states: set[str] = set()
    for q in queue_items:
        q_aid = str(q.get("alert_id", ""))
        q_analysis = str(q.get("analysis_id", ""))
        if (q_aid and q_aid in alert_ids) or (q_analysis and q_analysis in analysis_ids):
            status = str(q.get("status", "OPEN")).upper()
            if status in ("RESOLVED", "CLOSED"):
                states.add("resolved")
            elif status in ("IN_REVIEW", "IN REVIEW"):
                states.add("in_review")
            else:
                states.add("open")
    if "in_review" in states:
        return "in_review"
    if "open" in states:
        return "open"
    if "resolved" in states:
        return "resolved"
    return "none"


def _count_evidence(alert_ids: set[str], alerts: list[dict]) -> int:
    count = 0
    for a in alerts:
        aid = str(a.get("alert_id", ""))
        if aid in alert_ids:
            evidence = a.get("evidence") or a.get("evidence_bundle")
            if evidence:
                count += 1
    return count


def group_alerts(
    alerts: Sequence[Any] | None = None,
    queue_items: Sequence[Any] | None = None,
) -> list[AlertGroup]:
    """Group related alerts by shared attributes."""
    alert_list = [_get_dict(a) for a in (alerts or [])]
    queue_list = [_get_dict(q) for q in (queue_items or [])]

    if not alert_list:
        return []

    # Build groupings by key dimensions
    groupings: dict[str, dict[str, list[dict]]] = {
        "analysis_id": {},
        "location": {},
        "watchlist_id": {},
        "signal_type": {},
        "criterion": {},
    }

    for ad in alert_list:
        # Analysis grouping
        analysis_id = str(ad.get("analysis_id", ""))
        if analysis_id:
            groupings["analysis_id"].setdefault(analysis_id, []).append(ad)

        # Location grouping
        loc = ad.get("location_label") or ad.get("location")
        if loc and isinstance(loc, str) and loc.strip():
            groupings["location"].setdefault(loc.strip(), []).append(ad)

        # Watchlist grouping
        wl_id = str(ad.get("watchlist_id", ""))
        if wl_id:
            groupings["watchlist_id"].setdefault(wl_id, []).append(ad)

        # Signal type grouping
        sig_type = str(ad.get("signal_type", ad.get("type", "")))
        if sig_type:
            groupings["signal_type"].setdefault(sig_type, []).append(ad)

        # Criterion grouping
        criterion = str(ad.get("criterion", ad.get("criteria", "")))
        if criterion:
            groupings["criterion"].setdefault(criterion, []).append(ad)

    results: list[AlertGroup] = []
    seen_group_ids: set[str] = set()

    for key, value_map in groupings.items():
        for value, group_alerts_list in value_map.items():
            if len(group_alerts_list) < 2:
                continue  # No grouping for singletons

            member_ids = sorted({str(a.get("alert_id", "UNKNOWN")) for a in group_alerts_list})
            gid = _make_group_id(key, value)

            if gid in seen_group_ids:
                continue
            seen_group_ids.add(gid)

            # Title generation
            key_labels = {
                "analysis_id": f"Analysis {value}",
                "location": f"Location: {value}",
                "watchlist_id": f"Watchlist {value}",
                "signal_type": f"Signal Type: {value}",
                "criterion": f"Criterion: {value}",
            }
            title = key_labels.get(key, f"{key}: {value}")

            results.append(AlertGroup(
                group_id=gid,
                group_title=title,
                grouping_key=key,
                grouping_value=value,
                member_alert_ids=member_ids,
                dominant_severity=_dominant_severity(group_alerts_list),
                highest_priority=_highest_priority(group_alerts_list),
                evidence_count=_count_evidence(set(member_ids), alert_list),
                investigation_state=_investigation_state_for_group(group_alerts_list, queue_list),
            ))

    # Sort by dominant severity descending
    results.sort(key=lambda g: SEVERITY_RANK.get(g.dominant_severity, 0), reverse=True)
    return results
