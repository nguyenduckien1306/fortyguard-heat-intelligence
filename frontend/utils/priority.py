"""Deterministic Operational Priority Engine.

Calculates explainable priority scores for OperationalSignals based on measurable properties.

Strict Invariants:
1. Zero machine-learning claims or black-box heuristics.
2. Pure, deterministic mathematical evaluation.
3. Scoring formula explicitly combines severity, magnitude, recency, persistence, and data quality.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence

from frontend.utils.operational_intelligence import OperationalSignal

# Explicit scoring weights
SEVERITY_BASE_SCORES: dict[str, float] = {
    "CRITICAL": 40.0,
    "ELEVATED": 30.0,
    "WATCH": 20.0,
    "INFO": 10.0,
}

DATA_QUALITY_MULTIPLIERS: dict[str, float] = {
    "HIGH": 1.0,
    "MEDIUM": 0.85,
    "LOW": 0.70,
    "INSUFFICIENT": 0.40,
}

PERSISTENCE_TYPES: frozenset[str] = frozenset({
    "persistent_elevation",
    "temperature_increase",
    "high_spatial_spread",
    "high_hot_area_proportion",
})

PRIORITY_CRITICAL = "Critical"
PRIORITY_HIGH = "High"
PRIORITY_MEDIUM = "Medium"
PRIORITY_LOW = "Low"


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None


def calculate_magnitude_points(observed: float | None, threshold: float | None, metric: str | None) -> float:
    """Calculate points based on absolute difference from threshold (0 to 30 points)."""
    if observed is None or threshold is None:
        return 5.0  # baseline default magnitude

    diff = abs(observed - threshold)
    if "proportion" in str(metric).lower():
        # Proportion difference in percentage (0 to 100)
        norm_diff = diff / 50.0  # 50% diff = full 30 pts
    elif "spread" in str(metric).lower():
        norm_diff = diff / 10.0  # 10°C spread diff = full 30 pts
    elif "tile" in str(metric).lower():
        norm_diff = diff / 100.0
    else:
        # Temperature difference (e.g. 5°C exceedance = full 30 pts)
        norm_diff = diff / 5.0

    return min(30.0, max(0.0, norm_diff * 30.0))


def calculate_recency_points(created_at: str | None) -> float:
    """Calculate points based on observation recency (0 to 15 points)."""
    if not created_at:
        return 8.0

    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_hours = (now - dt).total_seconds() / 3600.0

        if age_hours <= 24:
            return 15.0
        elif age_hours <= 168:  # 7 days
            return 10.0
        elif age_hours <= 720:  # 30 days
            return 5.0
        else:
            return 2.0
    except (ValueError, TypeError):
        return 8.0


def calculate_persistence_points(signal_type: str | None) -> float:
    """Calculate points for temporal persistence or movement indicators (0 to 15 points)."""
    st_clean = str(signal_type or "").lower().strip()
    if st_clean in PERSISTENCE_TYPES:
        return 15.0
    elif "increase" in st_clean or "threshold" in st_clean:
        return 10.0
    elif "stability" in st_clean:
        return 5.0
    return 0.0


def calculate_priority_score(signal: OperationalSignal | Mapping[str, Any]) -> float:
    """Calculate the operational priority score for a signal (0 to 100)."""
    s_dict = signal.to_dict() if isinstance(signal, OperationalSignal) else dict(signal)

    sev = str(s_dict.get("severity", "INFO")).upper()
    base_sev = SEVERITY_BASE_SCORES.get(sev, 10.0)

    obs_val = _safe_float(s_dict.get("observed_value"))
    thresh_val = _safe_float(s_dict.get("threshold_value"))
    metric = s_dict.get("metric")
    mag_pts = calculate_magnitude_points(obs_val, thresh_val, metric)

    created_at = str(s_dict.get("created_at", ""))
    recency_pts = calculate_recency_points(created_at)

    sig_type = str(s_dict.get("signal_type", ""))
    persistence_pts = calculate_persistence_points(sig_type)

    # Sum components (max raw = 40 + 30 + 15 + 15 = 100)
    raw_score = base_sev + mag_pts + recency_pts + persistence_pts

    # Apply data quality multiplier
    dq = str(s_dict.get("data_quality", "HIGH")).upper()
    dq_mult = DATA_QUALITY_MULTIPLIERS.get(dq, 1.0)

    final_score = round(min(100.0, max(0.0, raw_score * dq_mult)), 2)
    return final_score


def classify_priority(score: float) -> str:
    """Classify a numeric score into a discrete priority level."""
    if score >= 75.0:
        return PRIORITY_CRITICAL
    elif score >= 50.0:
        return PRIORITY_HIGH
    elif score >= 30.0:
        return PRIORITY_MEDIUM
    else:
        return PRIORITY_LOW


def get_signal_priority(signal: OperationalSignal | Mapping[str, Any]) -> tuple[float, str]:
    """Get both the priority score and priority classification."""
    score = calculate_priority_score(signal)
    label = classify_priority(score)
    return score, label


def explain_priority_score(signal: OperationalSignal | Mapping[str, Any]) -> dict[str, Any]:
    """Return an explainable breakdown of how the priority score was derived.

    Pure relative to calculate_priority_score. Never invents missing evidence.
    """
    s_dict = signal.to_dict() if isinstance(signal, OperationalSignal) else dict(signal)

    severity = str(s_dict.get("severity", "INFO")).upper()
    base_sev = SEVERITY_BASE_SCORES.get(severity, 10.0)

    obs_val = _safe_float(s_dict.get("observed_value"))
    thresh_val = _safe_float(s_dict.get("threshold_value"))
    metric = s_dict.get("metric")
    mag_pts = calculate_magnitude_points(obs_val, thresh_val, metric)
    if obs_val is None or thresh_val is None:
        magnitude_note = "Magnitude uses baseline default because observed or threshold value is missing."
    else:
        magnitude_note = (
            f"Magnitude contribution {mag_pts} from observed={obs_val} vs threshold={thresh_val}."
        )

    created_at = str(s_dict.get("created_at", "")) or None
    recency_pts = calculate_recency_points(created_at)
    recency_note = (
        f"Recency contribution {recency_pts} from created_at='{created_at}'."
        if created_at
        else f"Recency contribution {recency_pts} (default; created_at missing)."
    )

    sig_type = str(s_dict.get("signal_type", ""))
    persistence_pts = calculate_persistence_points(sig_type)
    persistence_note = (
        f"Persistence contribution {persistence_pts} for signal_type='{sig_type}'."
        if persistence_pts
        else "No persistence contribution for this signal type."
    )

    dq = str(s_dict.get("data_quality", "HIGH")).upper()
    dq_mult = DATA_QUALITY_MULTIPLIERS.get(dq, 1.0)
    full_score = calculate_priority_score(signal)
    label = classify_priority(full_score)

    return {
        "score": full_score,
        "priority": label,
        "factors": {
            "severity_base": base_sev,
            "severity": severity,
            "magnitude_points": mag_pts,
            "magnitude_note": magnitude_note,
            "recency_points": recency_pts,
            "recency_note": recency_note,
            "persistence_points": persistence_pts,
            "persistence_note": persistence_note,
            "data_quality": dq,
            "data_quality_multiplier": dq_mult,
        },
        "explanation": (
            f"Priority {label} (score {full_score}) from severity={severity} ({base_sev}), "
            f"magnitude={mag_pts}, recency={recency_pts}, persistence={persistence_pts}, "
            f"data_quality={dq} (×{dq_mult})."
        ),
    }


def sort_signals_by_priority(signals: Sequence[OperationalSignal]) -> list[OperationalSignal]:
    """Deterministically sort operational signals by priority score descending."""
    scored: list[tuple[float, OperationalSignal]] = [
        (calculate_priority_score(s), s) for s in signals
    ]

    def _sort_key(item: tuple[float, OperationalSignal]) -> tuple[float, str, str]:
        score, sig = item
        return (-score, sig.created_at or "", sig.signal_id)

    scored.sort(key=_sort_key)
    return [s for _, s in scored]
