"""Deterministic Operator Action Recommendation Engine (Phase 17).

Generates UI workflow action suggestions — NOT real-world interventions.
All recommendations are application navigation actions only.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ActionRecommendation:
    """Immutable operator workflow action recommendation."""

    action_id: str
    title: str
    reason: str
    source_object_id: str
    source_object_type: str
    priority: float
    destination_ui_state: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return dict(obj.to_dict())
    if isinstance(obj, Mapping):
        return dict(obj)
    return {}


def _make_action_id(prefix: str, source_id: str) -> str:
    raw = f"{prefix}:{source_id}"
    return f"ACT-{hashlib.sha256(raw.encode()).hexdigest()[:10].upper()}"


SEVERITY_PRIORITY = {"CRITICAL": 90.0, "ELEVATED": 70.0, "WATCH": 40.0, "INFO": 15.0}


def generate_alert_actions(alerts: Sequence[Any]) -> list[ActionRecommendation]:
    """Generate workflow actions for unresolved alerts."""
    actions: list[ActionRecommendation] = []

    for a in alerts:
        ad = _get_dict(a)
        aid = str(ad.get("alert_id", "UNKNOWN"))
        status = str(ad.get("status", "ACTIVE")).upper()
        severity = str(ad.get("severity", "INFO")).upper()

        if status in ("RESOLVED", "DISMISSED"):
            continue

        base_priority = SEVERITY_PRIORITY.get(severity, 15.0)

        # Review evidence
        evidence = ad.get("evidence") or ad.get("evidence_bundle")
        if evidence:
            actions.append(ActionRecommendation(
                action_id=_make_action_id("review_evidence", aid),
                title=f"Review evidence bundle for Alert {aid}",
                reason=f"{severity} alert with evidence available for review.",
                source_object_id=aid,
                source_object_type="alert",
                priority=base_priority + 5,
                destination_ui_state="alert_detail",
            ))
        else:
            actions.append(ActionRecommendation(
                action_id=_make_action_id("investigate", aid),
                title=f"Investigate Alert {aid}",
                reason=f"{severity} alert without evidence — requires investigation.",
                source_object_id=aid,
                source_object_type="alert",
                priority=base_priority + 10,
                destination_ui_state="investigation_queue",
            ))

    return actions


def generate_investigation_actions(queue_items: Sequence[Any]) -> list[ActionRecommendation]:
    """Generate workflow actions for open investigations."""
    actions: list[ActionRecommendation] = []

    for q in queue_items:
        qd = _get_dict(q)
        qid = str(qd.get("queue_id", qd.get("item_id", "UNKNOWN")))
        status = str(qd.get("status", "OPEN")).upper()

        if status in ("RESOLVED", "CLOSED"):
            continue

        if status == "OPEN":
            actions.append(ActionRecommendation(
                action_id=_make_action_id("begin_review", qid),
                title=f"Begin review of Investigation {qid}",
                reason="Investigation is open and awaiting review.",
                source_object_id=qid,
                source_object_type="investigation",
                priority=60.0,
                destination_ui_state="investigation_detail",
            ))
        elif status in ("IN_REVIEW", "IN REVIEW"):
            actions.append(ActionRecommendation(
                action_id=_make_action_id("complete_review", qid),
                title=f"Complete review of Investigation {qid}",
                reason="Investigation is under review — consider resolving or escalating.",
                source_object_id=qid,
                source_object_type="investigation",
                priority=50.0,
                destination_ui_state="investigation_detail",
            ))

    return actions


def generate_comparison_actions(records: Sequence[Any]) -> list[ActionRecommendation]:
    """Generate actions suggesting comparison with previous analyses."""
    rec_list = [_get_dict(r) for r in records]
    if len(rec_list) < 2:
        return []

    # Sort by date
    dated = sorted(rec_list, key=lambda r: r.get("date", r.get("created_at", "")) or "")
    latest = dated[-1]
    previous = dated[-2]

    latest_aid = str(latest.get("analysis_id", "UNKNOWN"))
    prev_aid = str(previous.get("analysis_id", "UNKNOWN"))

    return [ActionRecommendation(
        action_id=_make_action_id("compare", f"{latest_aid}:{prev_aid}"),
        title=f"Compare analysis {latest_aid} with previous {prev_aid}",
        reason="Multiple analyses available. Review changes between observations.",
        source_object_id=latest_aid,
        source_object_type="analysis",
        priority=35.0,
        destination_ui_state="change_detection",
    )]


def generate_watchlist_actions(
    watchlist_evaluations: Sequence[Any],
) -> list[ActionRecommendation]:
    """Generate actions for triggered watchlists."""
    actions: list[ActionRecommendation] = []

    for we in watchlist_evaluations:
        wd = _get_dict(we)
        if not (wd.get("matched") or wd.get("status") == "TRIGGERED"):
            continue
        wl_id = str(wd.get("watchlist_id", "UNKNOWN"))
        actions.append(ActionRecommendation(
            action_id=_make_action_id("review_watchlist", wl_id),
            title=f"Review triggered watchlist {wl_id}",
            reason="Watchlist criteria matched — review configured thresholds.",
            source_object_id=wl_id,
            source_object_type="watchlist",
            priority=45.0,
            destination_ui_state="watchlist_detail",
        ))

    return actions


def generate_all_actions(
    alerts: Sequence[Any] | None = None,
    queue_items: Sequence[Any] | None = None,
    records: Sequence[Any] | None = None,
    watchlist_evaluations: Sequence[Any] | None = None,
) -> list[ActionRecommendation]:
    """Generate all operator actions and return sorted by priority descending."""
    actions: list[ActionRecommendation] = []
    actions.extend(generate_alert_actions(alerts or []))
    actions.extend(generate_investigation_actions(queue_items or []))
    actions.extend(generate_comparison_actions(records or []))
    actions.extend(generate_watchlist_actions(watchlist_evaluations or []))
    actions.sort(key=lambda a: a.priority, reverse=True)
    return actions
