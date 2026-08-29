"""User Configurable Alert Policy Management.

Session-local alert policy models and validation rules.

Strict Invariants:
1. Session-local storage only in st.session_state (zero DB, zero external disk/cloud).
2. Maximum 20 active policies.
3. Policy names maximum 60 characters.
4. No duplicate equivalent policies.
5. Rejects invalid thresholds, non-finite values, and invalid operators.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import math
from typing import Any, Mapping
import streamlit as st

_POLICIES_STORE_KEY = "_session_alert_policies"

MAX_ALERT_POLICIES = 20
MAX_POLICY_NAME_LENGTH = 60

SUPPORTED_METRICS: frozenset[str] = frozenset({
    "mean_temperature",
    "minimum_temperature",
    "maximum_temperature",
    "temperature_spread",
    "above_threshold_proportion",
    "tile_count",
})

SUPPORTED_OPERATORS: frozenset[str] = frozenset({">", ">=", "<", "<=", "=="})
SUPPORTED_SEVERITIES: frozenset[str] = frozenset({"INFO", "WATCH", "ELEVATED", "CRITICAL"})


@dataclass
class AlertPolicy:
    """Configurable alert policy applied against completed AnalysisRecords."""

    policy_id: str
    name: str
    metric: str
    operator: str
    threshold: float
    severity: str = "WATCH"  # "INFO" | "WATCH" | "ELEVATED" | "CRITICAL"
    applies_to: str = "all"  # "all" | "heatmap" | "heat_intelligence" or specific location
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AlertPolicy:
        thresh = data.get("threshold", 0.0)
        try:
            thresh_f = float(thresh)
        except (ValueError, TypeError):
            thresh_f = 0.0

        return cls(
            policy_id=str(data.get("policy_id", "")),
            name=str(data.get("name", "Untitled Policy")).strip(),
            metric=str(data.get("metric", "mean_temperature")).strip().lower(),
            operator=str(data.get("operator", ">")).strip(),
            threshold=thresh_f,
            severity=str(data.get("severity", "WATCH")).strip().upper(),
            applies_to=str(data.get("applies_to", "all")).strip(),
            enabled=bool(data.get("enabled", True)),
            created_at=str(data.get("created_at", datetime.now().isoformat())),
        )


def validate_alert_policy(policy: AlertPolicy | Mapping[str, Any]) -> tuple[bool, str | None]:
    """Validate an AlertPolicy against operational safety constraints."""
    p_dict = policy.to_dict() if isinstance(policy, AlertPolicy) else dict(policy)

    name = str(p_dict.get("name", "")).strip()
    if not name:
        return False, "Policy name cannot be empty."
    if len(name) > MAX_POLICY_NAME_LENGTH:
        return False, f"Policy name exceeds maximum allowed length of {MAX_POLICY_NAME_LENGTH} characters."

    metric = str(p_dict.get("metric", "")).strip().lower()
    if metric not in SUPPORTED_METRICS:
        return False, f"Invalid metric '{metric}'. Supported metrics: {', '.join(sorted(SUPPORTED_METRICS))}."

    op = str(p_dict.get("operator", "")).strip()
    if op not in SUPPORTED_OPERATORS:
        return False, f"Invalid operator '{op}'. Supported operators: {', '.join(sorted(SUPPORTED_OPERATORS))}."

    thresh = p_dict.get("threshold")
    if thresh is None:
        return False, "Threshold value cannot be None."
    try:
        thresh_f = float(thresh)
        if math.isnan(thresh_f) or math.isinf(thresh_f):
            return False, "Threshold must be a valid finite number."
    except (ValueError, TypeError):
        return False, "Threshold must be a numeric value."

    # Domain specific threshold checks
    if metric == "above_threshold_proportion":
        if thresh_f < 0.0 or thresh_f > 100.0:
            return False, "Above-threshold proportion must be between 0 and 100% (or 0.0 to 1.0)."
    elif metric == "tile_count":
        if thresh_f < 0.0:
            return False, "Tile count threshold cannot be negative."
    elif metric in ("mean_temperature", "minimum_temperature", "maximum_temperature"):
        if thresh_f < -100.0 or thresh_f > 100.0:
            return False, "Temperature threshold must be between -100°C and 100°C."
    elif metric == "temperature_spread":
        if thresh_f < 0.0 or thresh_f > 100.0:
            return False, "Temperature spread threshold must be non-negative."

    sev = str(p_dict.get("severity", "WATCH")).strip().upper()
    if sev not in SUPPORTED_SEVERITIES:
        return False, f"Invalid severity '{sev}'. Supported severities: {', '.join(sorted(SUPPORTED_SEVERITIES))}."

    return True, None


def are_policies_equivalent(p1: AlertPolicy, p2: AlertPolicy) -> bool:
    """Check if two policies evaluate the exact same condition."""
    return (
        p1.metric.lower() == p2.metric.lower()
        and p1.operator == p2.operator
        and abs(p1.threshold - p2.threshold) < 1e-6
        and p1.applies_to.lower() == p2.applies_to.lower()
        and p1.severity.upper() == p2.severity.upper()
    )


def get_default_alert_policies() -> list[AlertPolicy]:
    """Factory for standard baseline alert policies."""
    now = datetime.now().isoformat()
    return [
        AlertPolicy(
            policy_id="POL-CRIT-HEAT",
            name="Critical Temperature Alert",
            metric="mean_temperature",
            operator=">=",
            threshold=40.0,
            severity="CRITICAL",
            applies_to="all",
            enabled=True,
            created_at=now,
        ),
        AlertPolicy(
            policy_id="POL-ELEV-HEAT",
            name="Elevated Temperature Watch",
            metric="mean_temperature",
            operator=">=",
            threshold=35.0,
            severity="ELEVATED",
            applies_to="all",
            enabled=True,
            created_at=now,
        ),
        AlertPolicy(
            policy_id="POL-SPREAD-HIGH",
            name="High Thermal Variability",
            metric="temperature_spread",
            operator=">=",
            threshold=8.0,
            severity="ELEVATED",
            applies_to="all",
            enabled=True,
            created_at=now,
        ),
        AlertPolicy(
            policy_id="POL-HOT-PROPORTION",
            name="Widespread Hot Surface Area",
            metric="above_threshold_proportion",
            operator=">=",
            threshold=40.0,
            severity="ELEVATED",
            applies_to="all",
            enabled=True,
            created_at=now,
        ),
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Session Storage Manager
# ──────────────────────────────────────────────────────────────────────────────


def get_alert_policies() -> list[AlertPolicy]:
    """Retrieve all alert policies from active session state."""
    if _POLICIES_STORE_KEY not in st.session_state:
        st.session_state[_POLICIES_STORE_KEY] = [p.to_dict() for p in get_default_alert_policies()]

    raw_list = st.session_state.get(_POLICIES_STORE_KEY, [])
    return [AlertPolicy.from_dict(d) for d in raw_list if isinstance(d, Mapping)]


def save_alert_policy(policy: AlertPolicy | Mapping[str, Any]) -> tuple[bool, str | None]:
    """Add or update an alert policy in session state."""
    is_valid, err = validate_alert_policy(policy)
    if not is_valid:
        return False, err

    pol_obj = policy if isinstance(policy, AlertPolicy) else AlertPolicy.from_dict(policy)
    if not pol_obj.policy_id:
        pol_obj.policy_id = f"POL-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"

    current = get_alert_policies()

    # Check capacity limit
    is_existing = any(p.policy_id == pol_obj.policy_id for p in current)
    if not is_existing and len(current) >= MAX_ALERT_POLICIES:
        return False, f"Maximum policy limit ({MAX_ALERT_POLICIES}) reached. Delete an existing policy first."

    # Check for duplicate equivalent policy
    for existing in current:
        if existing.policy_id != pol_obj.policy_id and are_policies_equivalent(existing, pol_obj):
            return False, f"An equivalent policy already exists: '{existing.name}'."

    # Insert or update
    updated_list: list[AlertPolicy] = []
    found = False
    for p in current:
        if p.policy_id == pol_obj.policy_id:
            updated_list.append(pol_obj)
            found = True
        else:
            updated_list.append(p)

    if not found:
        updated_list.append(pol_obj)

    st.session_state[_POLICIES_STORE_KEY] = [p.to_dict() for p in updated_list]
    return True, None


def delete_alert_policy(policy_id: str) -> tuple[bool, str | None]:
    """Delete an alert policy by ID from session state."""
    current = get_alert_policies()
    updated = [p for p in current if p.policy_id != policy_id]
    if len(updated) == len(current):
        return False, f"Policy '{policy_id}' not found."

    st.session_state[_POLICIES_STORE_KEY] = [p.to_dict() for p in updated]
    return True, None


def toggle_alert_policy(policy_id: str, enabled: bool | None = None) -> tuple[bool, str | None]:
    """Toggle or set the enabled status of an alert policy."""
    current = get_alert_policies()
    found = False
    for p in current:
        if p.policy_id == policy_id:
            p.enabled = (not p.enabled) if enabled is None else enabled
            found = True
            break

    if not found:
        return False, f"Policy '{policy_id}' not found."

    st.session_state[_POLICIES_STORE_KEY] = [p.to_dict() for p in current]
    return True, None


def reset_default_alert_policies() -> None:
    """Reset session policies back to initial defaults."""
    st.session_state[_POLICIES_STORE_KEY] = [p.to_dict() for p in get_default_alert_policies()]
