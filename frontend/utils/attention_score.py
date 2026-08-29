"""Operator Attention Scoring Engine (Phase 17).

Secondary attention score distinct from the existing priority system.
Answers: "Which item should an operator inspect first?"
Combines priority, age, recurrence, investigation state, evidence availability,
and data quality limitations into a single composite attention score.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from frontend.utils.clock import Clock, get_current_clock


@dataclass(frozen=True)
class AttentionScore:
    """Immutable operator attention score for an alert or investigation item."""

    item_id: str
    item_type: str  # "alert" | "investigation" | "signal"
    attention_score: float
    priority_component: float
    age_component: float
    recurrence_component: float
    investigation_component: float
    evidence_component: float
    data_quality_component: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return dict(obj.to_dict())
    if isinstance(obj, Mapping):
        return dict(obj)
    return {}


def _safe_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


SEVERITY_SCORES = {"CRITICAL": 40.0, "ELEVATED": 30.0, "WATCH": 15.0, "INFO": 5.0}
DQ_PENALTY = {"HIGH": 0.0, "MEDIUM": -3.0, "LOW": -8.0, "INSUFFICIENT": -15.0}
INVESTIGATION_BONUS = {"none": 5.0, "open": 3.0, "in_review": 1.0, "resolved": 0.0}

# Weights
W_PRIORITY = 1.0
W_AGE = 0.3
W_RECURRENCE = 0.2
W_INVESTIGATION = 0.15
W_EVIDENCE = 0.1
W_DATA_QUALITY = 0.1


def _compute_age_score(created_at: str | None, clock: Clock) -> float:
    """Higher score for newer unresolved items (recency bonus)."""
    if not created_at:
        return 5.0  # Default moderate score
    try:
        from frontend.utils.clock import _parse_iso_datetime
        created = _parse_iso_datetime(str(created_at))
        now = clock.now()
        # Make both timezone-aware or both naive
        if created.tzinfo is not None and now.tzinfo is None:
            from datetime import timezone
            now = now.replace(tzinfo=timezone.utc)
        elif created.tzinfo is None and now.tzinfo is not None:
            from datetime import timezone
            created = created.replace(tzinfo=timezone.utc)
        age_hours = max(0, (now - created).total_seconds() / 3600)
        # Recent items get higher attention: max 10, decays over 24h
        return max(0.0, min(10.0, 10.0 - (age_hours / 2.4)))
    except Exception:
        return 5.0


def compute_attention_score(
    item: Any,
    item_type: str = "alert",
    recurrence_count: int = 0,
    investigation_state: str = "none",
    has_evidence: bool = False,
    clock: Clock | None = None,
) -> AttentionScore:
    """Compute composite attention score for a single item."""
    clk = clock or get_current_clock()
    d = _get_dict(item)

    item_id = str(d.get("alert_id", d.get("signal_id", d.get("queue_id", d.get("item_id", "UNKNOWN")))))

    # Priority component
    severity = str(d.get("severity", "INFO")).upper()
    priority_raw = _safe_float(d.get("priority_score", d.get("priority", 0)))
    priority_component = max(priority_raw, SEVERITY_SCORES.get(severity, 5.0))

    # Age component
    created_at = d.get("created_at", d.get("timestamp"))
    age_component = _compute_age_score(created_at, clk)

    # Recurrence component (more recurrences = more attention)
    recurrence_component = min(20.0, recurrence_count * 5.0)

    # Investigation component (uninvestigated items need more attention)
    investigation_component = INVESTIGATION_BONUS.get(investigation_state, 5.0)

    # Evidence component (items without evidence need investigation)
    evidence_component = 0.0 if has_evidence else 8.0

    # Data quality component
    dq = str(d.get("data_quality", "HIGH")).upper()
    data_quality_component = DQ_PENALTY.get(dq, 0.0)

    # Composite score
    attention_score = max(0.0, (
        W_PRIORITY * priority_component
        + W_AGE * age_component
        + W_RECURRENCE * recurrence_component
        + W_INVESTIGATION * investigation_component
        + W_EVIDENCE * evidence_component
        + W_DATA_QUALITY * data_quality_component
    ))

    # Explanation
    parts = []
    if severity in ("CRITICAL", "ELEVATED"):
        parts.append(f"{severity} severity")
    if recurrence_count > 0:
        parts.append(f"{recurrence_count} recurrence(s)")
    if investigation_state == "none":
        parts.append("not yet investigated")
    if not has_evidence:
        parts.append("no evidence collected")
    if dq in ("LOW", "INSUFFICIENT"):
        parts.append(f"{dq} data quality")

    explanation = "; ".join(parts) if parts else "Standard priority item."

    return AttentionScore(
        item_id=item_id,
        item_type=item_type,
        attention_score=round(attention_score, 2),
        priority_component=round(priority_component, 2),
        age_component=round(age_component, 2),
        recurrence_component=round(recurrence_component, 2),
        investigation_component=round(investigation_component, 2),
        evidence_component=round(evidence_component, 2),
        data_quality_component=round(data_quality_component, 2),
        explanation=explanation,
    )


def rank_by_attention(
    items: Sequence[Any],
    item_type: str = "alert",
    recurrence_map: dict[str, int] | None = None,
    investigation_map: dict[str, str] | None = None,
    evidence_set: set[str] | None = None,
    clock: Clock | None = None,
) -> list[AttentionScore]:
    """Rank multiple items by attention score (descending)."""
    rec_map = recurrence_map or {}
    inv_map = investigation_map or {}
    ev_set = evidence_set or set()
    clk = clock or get_current_clock()

    scores: list[AttentionScore] = []
    for item in items:
        d = _get_dict(item)
        item_id = str(d.get("alert_id", d.get("signal_id", d.get("queue_id", d.get("item_id", "UNKNOWN")))))
        score = compute_attention_score(
            item=item,
            item_type=item_type,
            recurrence_count=rec_map.get(item_id, 0),
            investigation_state=inv_map.get(item_id, "none"),
            has_evidence=item_id in ev_set,
            clock=clk,
        )
        scores.append(score)

    scores.sort(key=lambda s: s.attention_score, reverse=True)
    return scores
