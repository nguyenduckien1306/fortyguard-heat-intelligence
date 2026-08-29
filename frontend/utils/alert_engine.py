"""Pure Deterministic Alert Evaluation and Signal Lifecycle Engine.

Evaluates user-configured AlertPolicies against completed AnalysisRecords and manages signal lifecycles.

Strict Invariants:
1. Zero network I/O, zero HTTP requests, zero background loops.
2. Pure evaluation function: identical inputs produce identical outputs.
3. Only completed AnalysisRecord instances are evaluated.
4. Session-only lifecycle persistence
   (NEW, ACKNOWLEDGED, INVESTIGATING, RESOLVED, DISMISSED).
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Mapping, Sequence
import streamlit as st

from frontend.utils.alert_policies import AlertPolicy
from frontend.utils.operational_intelligence import (
    SEVERITY_WEIGHTS,
    OperationalSignal,
    _determine_record_data_quality,
    _extract_metric_val,
)

_LIFECYCLE_STORE_KEY = "_session_signal_lifecycle_store"

LIFECYCLE_NEW = "NEW"
LIFECYCLE_ACKNOWLEDGED = "ACKNOWLEDGED"
LIFECYCLE_INVESTIGATING = "INVESTIGATING"
LIFECYCLE_RESOLVED = "RESOLVED"
LIFECYCLE_DISMISSED = "DISMISSED"

VALID_LIFECYCLES: frozenset[str] = frozenset({
    LIFECYCLE_NEW,
    LIFECYCLE_ACKNOWLEDGED,
    LIFECYCLE_INVESTIGATING,
    LIFECYCLE_RESOLVED,
    LIFECYCLE_DISMISSED,
})

# Legal transitions for strict lifecycle control (session-local only).
LIFECYCLE_TRANSITIONS: dict[str, frozenset[str]] = {
    LIFECYCLE_NEW: frozenset({
        LIFECYCLE_ACKNOWLEDGED,
        LIFECYCLE_INVESTIGATING,
        LIFECYCLE_DISMISSED,
    }),
    LIFECYCLE_ACKNOWLEDGED: frozenset({
        LIFECYCLE_INVESTIGATING,
        LIFECYCLE_DISMISSED,
        LIFECYCLE_NEW,
        LIFECYCLE_RESOLVED,
    }),
    LIFECYCLE_INVESTIGATING: frozenset({
        LIFECYCLE_RESOLVED,
        LIFECYCLE_DISMISSED,
        LIFECYCLE_ACKNOWLEDGED,
    }),
    LIFECYCLE_RESOLVED: frozenset({
        LIFECYCLE_NEW,
        LIFECYCLE_DISMISSED,
    }),
    LIFECYCLE_DISMISSED: frozenset({
        LIFECYCLE_NEW,
    }),
}


# ──────────────────────────────────────────────────────────────────────────────
# Metric Mapping
# ──────────────────────────────────────────────────────────────────────────────

METRIC_CANDIDATE_KEYS: dict[str, list[str]] = {
    "mean_temperature": ["mean_temp", "mean_temperature", "observed_temperature", "temperature"],
    "minimum_temperature": ["min_temp", "min_temperature"],
    "maximum_temperature": ["max_temp", "max_temperature"],
    "temperature_spread": ["temp_spread", "temperature_spread", "spread"],
    "above_threshold_proportion": ["above_threshold_proportion", "hot_tile_pct"],
    "tile_count": ["total_tiles", "tile_count"],
}


def _matches_operator(observed: float, operator: str, threshold: float, tolerance: float = 1e-6) -> bool:
    """Evaluate a numeric condition deterministically."""
    if operator == ">":
        return observed > threshold + tolerance
    elif operator == ">=":
        return observed >= threshold - tolerance
    elif operator == "<":
        return observed < threshold - tolerance
    elif operator == "<=":
        return observed <= threshold + tolerance
    elif operator == "==":
        return abs(observed - threshold) <= tolerance
    return False


def _matches_scope(record_dict: Mapping[str, Any], applies_to: str) -> bool:
    """Check if a policy scope matches the given record."""
    if not applies_to or applies_to.lower() == "all":
        return True

    scope_clean = applies_to.lower().strip()
    atype = str(record_dict.get("analysis_type", "")).lower().strip()
    loc = str(record_dict.get("location_label", "")).lower().strip()

    if scope_clean in ("heatmap", "heat_intelligence"):
        return scope_clean in atype
    return scope_clean in loc or scope_clean in atype


# ──────────────────────────────────────────────────────────────────────────────
# Pure Policy Evaluation
# ──────────────────────────────────────────────────────────────────────────────


def evaluate_alert_policies(
    records: Sequence[Any],
    policies: Sequence[AlertPolicy | Mapping[str, Any]],
) -> list[OperationalSignal]:
    """Pure, deterministic evaluation of alert policies against completed records.

    Returns:
        Deduplicated, sorted list of OperationalSignal objects.
    """
    completed_recs = [
        r for r in records
        if (getattr(r, "status", None) == "Completed" or (isinstance(r, dict) and r.get("status") == "Completed"))
    ]

    active_policies: list[AlertPolicy] = []
    for p in policies:
        pol_obj = p if isinstance(p, AlertPolicy) else AlertPolicy.from_dict(p)
        if pol_obj.enabled:
            active_policies.append(pol_obj)

    generated_signals: list[OperationalSignal] = []

    for r in completed_recs:
        r_dict = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        aid = str(r_dict.get("analysis_id") or r_dict.get("activity_id") or "UNKNOWN")
        loc = str(r_dict.get("location_label") or "Analysis Area")
        created = str(r_dict.get("created_at") or datetime.now().isoformat())
        dq = _determine_record_data_quality(r_dict)

        for pol in active_policies:
            if not _matches_scope(r_dict, pol.applies_to):
                continue

            candidate_keys = METRIC_CANDIDATE_KEYS.get(pol.metric, [pol.metric])
            obs_val = _extract_metric_val(r_dict, candidate_keys)
            if obs_val is None:
                continue

            # Check proportion normalization
            eval_val = obs_val
            if pol.metric == "above_threshold_proportion":
                # Normalize both to percentage 0-100 for comparison if threshold > 1.0
                if pol.threshold > 1.0 and eval_val <= 1.0:
                    eval_val = eval_val * 100.0
                elif pol.threshold <= 1.0 and eval_val > 1.0:
                    eval_val = eval_val / 100.0

            if _matches_operator(eval_val, pol.operator, pol.threshold):
                diff = round(eval_val - pol.threshold, 2)
                direction = "above" if diff > 0 else ("below" if diff < 0 else "equal")

                # Unit string
                unit_str = "°C" if "temp" in pol.metric else ("%" if "proportion" in pol.metric else "tiles")

                sig_id = f"SIG-POL-{pol.policy_id}-{aid}"
                generated_signals.append(
                    OperationalSignal(
                        signal_id=sig_id,
                        analysis_id=aid,
                        signal_type=f"policy_{pol.metric}",
                        severity=pol.severity.upper(),
                        title=f"{pol.name} ({loc})",
                        description=f"Policy condition '{pol.metric} {pol.operator} {pol.threshold}{unit_str}' was met with observed value of {eval_val:.1f}{unit_str}.",
                        metric=pol.metric,
                        observed_value=eval_val,
                        threshold_value=pol.threshold,
                        direction=direction,
                        confidence="HIGH" if dq in ("HIGH", "MEDIUM") else "LOW",
                        evidence=[
                            f"Policy: {pol.name} [{pol.policy_id}]",
                            f"Observed: {eval_val:.2f}{unit_str}",
                            f"Threshold: {pol.operator} {pol.threshold:.2f}{unit_str}",
                            f"Difference: {diff:+.2f}{unit_str}",
                            f"Analysis ID: {aid} ({loc})",
                        ],
                        data_quality=dq,
                        created_at=created,
                    )
                )

    deduped = deduplicate_signals(generated_signals)

    # Sort: Severity descending, created_at descending, analysis_id ascending
    def _sort_key(s: OperationalSignal) -> tuple[int, str, str]:
        w = SEVERITY_WEIGHTS.get(s.severity, 0)
        return (-w, s.created_at or "", s.analysis_id)

    deduped.sort(key=_sort_key)
    return deduped


# ──────────────────────────────────────────────────────────────────────────────
# Signal Deduplication
# ──────────────────────────────────────────────────────────────────────────────


def deduplicate_signals(signals: Sequence[OperationalSignal]) -> list[OperationalSignal]:
    """Deduplicate operational signals by signal_id, keeping the latest occurrence."""
    seen: dict[str, OperationalSignal] = {}
    for s in signals:
        key = s.signal_id
        seen[key] = s
    return list(seen.values())


# ──────────────────────────────────────────────────────────────────────────────
# Signal Lifecycle Management (Session State)
# ──────────────────────────────────────────────────────────────────────────────


def _get_lifecycle_store() -> dict[str, dict[str, Any]]:
    """Retrieve raw lifecycle store from session state."""
    if _LIFECYCLE_STORE_KEY not in st.session_state:
        st.session_state[_LIFECYCLE_STORE_KEY] = {}
    return st.session_state[_LIFECYCLE_STORE_KEY]


def get_signal_lifecycle_status(signal_id: str) -> str:
    """Get the active lifecycle status for a signal ID."""
    store = _get_lifecycle_store()
    entry = store.get(signal_id, {})
    return str(entry.get("status", LIFECYCLE_NEW)).upper()


def can_transition_lifecycle(current: str, target: str) -> bool:
    """Return True when target is a legal transition from current."""
    cur = (current or LIFECYCLE_NEW).upper()
    tgt = (target or "").upper()
    if tgt not in VALID_LIFECYCLES:
        return False
    if cur not in LIFECYCLE_TRANSITIONS:
        return False
    return tgt in LIFECYCLE_TRANSITIONS[cur]


def transition_signal_lifecycle(
    signal_id: str,
    target_status: str,
    *,
    enforce: bool = True,
) -> tuple[bool, str | None]:
    """Transition a signal lifecycle state with optional validation.

    Returns:
        (ok, error_message). When enforce=False, applies any valid lifecycle label.
    """
    target = (target_status or "").upper()
    if target not in VALID_LIFECYCLES:
        return False, f"Invalid lifecycle status '{target_status}'."

    current = get_signal_lifecycle_status(signal_id)
    if enforce and not can_transition_lifecycle(current, target):
        return False, f"Illegal lifecycle transition: {current} -> {target}."

    store = _get_lifecycle_store()
    store[signal_id] = {
        "status": target,
        "updated_at": datetime.now().isoformat(),
        "previous_status": current,
    }
    st.session_state[_LIFECYCLE_STORE_KEY] = store
    return True, None


def acknowledge_signal(signal_id: str) -> bool:
    """Transition a signal to ACKNOWLEDGED state."""
    ok, _ = transition_signal_lifecycle(
        signal_id,
        LIFECYCLE_ACKNOWLEDGED,
        enforce=False,
    )
    return ok


def start_investigating_signal(signal_id: str) -> tuple[bool, str | None]:
    """Transition a signal to INVESTIGATING (strict transitions enforced)."""
    return transition_signal_lifecycle(signal_id, LIFECYCLE_INVESTIGATING, enforce=True)


def resolve_signal(signal_id: str) -> tuple[bool, str | None]:
    """Transition a signal to RESOLVED (strict transitions enforced)."""
    return transition_signal_lifecycle(signal_id, LIFECYCLE_RESOLVED, enforce=True)


def dismiss_signal(signal_id: str) -> bool:
    """Transition a signal to DISMISSED state."""
    ok, _ = transition_signal_lifecycle(
        signal_id,
        LIFECYCLE_DISMISSED,
        enforce=False,
    )
    return ok


def restore_signal(signal_id: str) -> bool:
    """Restore a signal back to NEW state."""
    ok, _ = transition_signal_lifecycle(
        signal_id,
        LIFECYCLE_NEW,
        enforce=False,
    )
    return ok


def filter_signals_by_lifecycle(
    signals: Sequence[OperationalSignal],
    status: str,
) -> list[OperationalSignal]:
    """Filter signals by their session-local lifecycle state."""
    target_status = status.upper()
    return [s for s in signals if get_signal_lifecycle_status(s.signal_id) == target_status]


def get_active_signals(
    signals: Sequence[OperationalSignal],
    include_acknowledged: bool = True,
) -> list[OperationalSignal]:
    """Get non-dismissed / non-resolved active operational signals."""
    allowed = {LIFECYCLE_NEW, LIFECYCLE_INVESTIGATING}
    if include_acknowledged:
        allowed.add(LIFECYCLE_ACKNOWLEDGED)
    return [s for s in signals if get_signal_lifecycle_status(s.signal_id) in allowed]


# ──────────────────────────────────────────────────────────────────────────────
# Phase 15 Alert Promotion, Escalation & Fatigue Cooldown
# ──────────────────────────────────────────────────────────────────────────────

from dataclasses import asdict, dataclass, field
import hashlib
import json
from frontend.utils.clock import Clock, get_current_clock, parse_timestamp_safe
from frontend.utils.priority import get_signal_priority

_ACTIVE_ALERTS_STORE_KEY = "_session_active_alerts_store"
_ALERT_COOLDOWN_STORE_KEY = "_session_alert_cooldown_store"

MAX_ACTIVE_ALERTS: int = 50

# Suppression Reason Codes
SUPPRESSION_COOLDOWN = "COOLDOWN"
SUPPRESSION_LOW_DATA_QUALITY = "LOW_DATA_QUALITY"
SUPPRESSION_POLICY_FILTER = "POLICY_FILTER"
SUPPRESSION_DUPLICATE = "DUPLICATE"
SUPPRESSION_USER_SUPPRESSED = "USER_SUPPRESSED"
SUPPRESSION_CAPACITY_LIMIT = "CAPACITY_LIMIT"

# Cooldown Windows in Seconds
COOLDOWN_SECONDS: dict[str, float] = {
    "15m": 15 * 60.0,
    "1h": 3600.0,
    "6h": 6 * 3600.0,
    "24h": 24 * 3600.0,
}


@dataclass
class AlertItem:
    """Represents an active or historical promoted Alert."""

    alert_id: str
    alert_fingerprint: str
    signal_id: str
    policy_id: str
    policy_name: str
    analysis_id: str
    location: str
    severity: str
    priority_score: float
    priority_tier: str
    escalation_level: str = "NORMAL"  # "NORMAL" | "ELEVATED" | "HIGH" | "CRITICAL"
    status: str = LIFECYCLE_NEW  # NEW | ACKNOWLEDGED | INVESTIGATING | RESOLVED | DISMISSED
    parent_alert_id: str | None = None
    trigger_count: int = 1
    cooldown_until: str | None = None
    evidence: list[str] = field(default_factory=list)
    promotion_reason: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AlertItem:
        return cls(
            alert_id=str(data.get("alert_id", "")),
            alert_fingerprint=str(data.get("alert_fingerprint", "")),
            signal_id=str(data.get("signal_id", "")),
            policy_id=str(data.get("policy_id", "")),
            policy_name=str(data.get("policy_name", "Alert Policy")),
            analysis_id=str(data.get("analysis_id", "")),
            location=str(data.get("location", "Analysis Area")),
            severity=str(data.get("severity", "WATCH")).upper(),
            priority_score=float(data.get("priority_score", 50.0)),
            priority_tier=str(data.get("priority_tier", "Medium")),
            escalation_level=str(data.get("escalation_level", "NORMAL")),
            status=str(data.get("status", LIFECYCLE_NEW)).upper(),
            parent_alert_id=data.get("parent_alert_id"),
            trigger_count=int(data.get("trigger_count", 1)),
            cooldown_until=data.get("cooldown_until"),
            evidence=list(data.get("evidence", [])),
            promotion_reason=str(data.get("promotion_reason", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )


def generate_alert_fingerprint(
    policy_id: str,
    signal_id: str,
    analysis_id: str,
    location: str = "",
) -> str:
    """Generate a distinct canonical SHA-256 identity fingerprint for an Alert."""
    raw = {
        "policy_id": str(policy_id).strip(),
        "signal_id": str(signal_id).strip(),
        "analysis_id": str(analysis_id).strip(),
        "location": str(location).strip().lower(),
    }
    canonical_str = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def _get_active_alerts_store() -> list[dict[str, Any]]:
    if _ACTIVE_ALERTS_STORE_KEY not in st.session_state:
        st.session_state[_ACTIVE_ALERTS_STORE_KEY] = []
    return st.session_state[_ACTIVE_ALERTS_STORE_KEY]


def get_active_alerts() -> list[AlertItem]:
    """Retrieve all active promoted alerts from session state."""
    raw = _get_active_alerts_store()
    return [AlertItem.from_dict(d) for d in raw if isinstance(d, Mapping)]


def promote_signals_to_alerts(
    signals: Sequence[Any],
    policies: Sequence[AlertPolicy],
    clock: Clock | None = None,
    cooldown_window: str = "1h",
) -> tuple[list[AlertItem], dict[str, Any]]:
    """Evaluate signals against policies with escalation, cooldown, and capacity gating."""
    clk = clock or get_current_clock()
    now_dt = clk.now()
    now_iso = clk.now_iso()
    cooldown_dur = COOLDOWN_SECONDS.get(cooldown_window, 3600.0)

    alerts_store = _get_active_alerts_store()
    existing_alerts: list[AlertItem] = [AlertItem.from_dict(d) for d in alerts_store if isinstance(d, Mapping)]
    active_by_fp: dict[str, AlertItem] = {a.alert_fingerprint: a for a in existing_alerts}

    # Diagnostics counters
    promoted_count = 0
    cooldown_suppressed = 0
    low_quality_suppressed = 0
    policy_filtered = 0
    capacity_suppressed = 0

    active_policies = [p for p in policies if p.enabled]

    for sig_raw in signals:
        sig = sig_raw if isinstance(sig_raw, OperationalSignal) else OperationalSignal.from_dict(sig_raw)
        dq = sig.data_quality.upper()

        # Gate 1: Data Quality Check
        if dq == "INSUFFICIENT":
            low_quality_suppressed += 1
            continue

        score, priority_tier = get_signal_priority(sig)

        for pol in active_policies:
            # Policy matching
            applies = pol.applies_to.lower()
            if applies != "all" and applies not in sig.title.lower() and applies not in sig.description.lower():
                policy_filtered += 1
                continue

            alert_fp = generate_alert_fingerprint(
                policy_id=pol.policy_id,
                signal_id=sig.signal_id,
                analysis_id=sig.analysis_id,
            )

            # Check existing alert with same fingerprint
            existing = active_by_fp.get(alert_fp)
            if existing:
                # Check cooldown
                if existing.cooldown_until:
                    cd_dt = parse_timestamp_safe(existing.cooldown_until, default_time=now_dt)
                    if now_dt < cd_dt and existing.status != LIFECYCLE_RESOLVED:
                        cooldown_suppressed += 1
                        continue

                # Escalation on repeated breach
                if existing.status in (LIFECYCLE_NEW, LIFECYCLE_ACKNOWLEDGED, LIFECYCLE_INVESTIGATING):
                    existing.trigger_count += 1
                    existing.updated_at = now_iso
                    # Escalate level
                    if existing.trigger_count >= 3:
                        existing.escalation_level = "CRITICAL"
                        existing.severity = "CRITICAL"
                    elif existing.trigger_count >= 2:
                        existing.escalation_level = "HIGH"
                    continue

            # Check capacity limit (50)
            active_count = sum(1 for a in existing_alerts if a.status in (LIFECYCLE_NEW, LIFECYCLE_ACKNOWLEDGED, LIFECYCLE_INVESTIGATING))
            if active_count >= MAX_ACTIVE_ALERTS:
                capacity_suppressed += 1
                continue

            # Create New Alert
            parent_id = existing.alert_id if (existing and existing.status == LIFECYCLE_RESOLVED) else None
            alert_id = f"ALT-{alert_fp[:10]}"
            from datetime import timedelta
            cd_until_iso = (now_dt + timedelta(seconds=cooldown_dur)).isoformat()

            new_alert = AlertItem(
                alert_id=alert_id,
                alert_fingerprint=alert_fp,
                signal_id=sig.signal_id,
                policy_id=pol.policy_id,
                policy_name=pol.name,
                analysis_id=sig.analysis_id,
                location=sig.title.split(":")[-1].strip() if ":" in sig.title else "Analysis Area",
                severity=pol.severity if pol.severity != "INFO" else sig.severity,
                priority_score=score,
                priority_tier=priority_tier,
                escalation_level="NORMAL",
                status=LIFECYCLE_NEW,
                parent_alert_id=parent_id,
                trigger_count=1,
                cooldown_until=cd_until_iso,
                evidence=list(sig.evidence),
                promotion_reason=f"Matched policy '{pol.name}' with priority {priority_tier} ({score:.0f}).",
                created_at=now_iso,
                updated_at=now_iso,
            )
            existing_alerts.append(new_alert)
            active_by_fp[alert_fp] = new_alert
            promoted_count += 1

    # Save to session store
    st.session_state[_ACTIVE_ALERTS_STORE_KEY] = [a.to_dict() for a in existing_alerts]

    diagnostics = {
        "promoted_count": promoted_count,
        "cooldown_suppressed": cooldown_suppressed,
        "low_quality_suppressed": low_quality_suppressed,
        "policy_filtered": policy_filtered,
        "capacity_suppressed": capacity_suppressed,
        "total_suppressed": cooldown_suppressed + low_quality_suppressed + policy_filtered + capacity_suppressed,
    }

    return existing_alerts, diagnostics


def explain_alert_decision(
    signal: Any,
    policies: Sequence[AlertPolicy],
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Provide structured explanation of why a signal was or was not promoted to an alert."""
    sig = signal if isinstance(signal, OperationalSignal) else OperationalSignal.from_dict(signal)
    dq = sig.data_quality.upper()
    score, priority_tier = get_signal_priority(sig)

    if dq == "INSUFFICIENT":
        return {
            "promoted": False,
            "suppression_reason": SUPPRESSION_LOW_DATA_QUALITY,
            "explanation": "Signal data quality is INSUFFICIENT; suppressed to prevent false positive alerts.",
            "data_quality": dq,
            "priority_tier": priority_tier,
        }

    matched_policy: AlertPolicy | None = None
    for p in policies:
        if p.enabled and (p.applies_to.lower() == "all" or p.applies_to.lower() in sig.title.lower()):
            matched_policy = p
            break

    if not matched_policy:
        return {
            "promoted": False,
            "suppression_reason": SUPPRESSION_POLICY_FILTER,
            "explanation": "No active alert policy matched this signal's criteria or scope.",
            "data_quality": dq,
            "priority_tier": priority_tier,
        }

    return {
        "promoted": True,
        "matched_policy_id": matched_policy.policy_id,
        "matched_policy_name": matched_policy.name,
        "explanation": f"Signal matched active policy '{matched_policy.name}' with {priority_tier} priority ({score:.0f}).",
        "data_quality": dq,
        "priority_tier": priority_tier,
    }


def clear_alert_stores() -> None:
    """Clear active alerts and cooldown caches from session storage."""
    if _ACTIVE_ALERTS_STORE_KEY in st.session_state:
        del st.session_state[_ACTIVE_ALERTS_STORE_KEY]
    if _ALERT_COOLDOWN_STORE_KEY in st.session_state:
        del st.session_state[_ALERT_COOLDOWN_STORE_KEY]


def resolve_alert(alert_id: str, resolution_reason: str = "") -> bool:
    """Mark an active alert as RESOLVED in session store."""
    raw = st.session_state.get(_ACTIVE_ALERTS_STORE_KEY, [])
    updated = False
    new_list = []
    for item in raw:
        d = dict(item) if isinstance(item, Mapping) else item.to_dict()
        if d.get("alert_id") == alert_id:
            d["status"] = LIFECYCLE_RESOLVED
            if resolution_reason:
                d["resolution_reason"] = resolution_reason
            updated = True
        new_list.append(d)
    if updated:
        st.session_state[_ACTIVE_ALERTS_STORE_KEY] = new_list
    return updated

