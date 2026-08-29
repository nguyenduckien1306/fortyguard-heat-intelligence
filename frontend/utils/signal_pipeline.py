"""Phase 15 Signal Pipeline & Deterministic Deduplication Engine.

Generates immutable OperationalSignal detection events with deterministic SHA-256
fingerprints and explicit signal precedence. Manages mutable SignalDisposition states.

Strict Invariants:
1. Zero HTTP / Network I/O.
2. Signal Precedence:
   WATCHLIST_MATCH > THRESHOLD_BREACH > RAPID_CHANGE > SIGNIFICANT_CHANGE > REPEATED_HEAT > DATA_ANOMALY.
3. Deterministic SHA-256 fingerprinting: repeated reruns produce identical signals without duplication.
4. Distinguishes multiple independent signals from duplicate signals on the same analysis.
5. Signal dispositions (NEW, ACKNOWLEDGED, LINKED_TO_ALERT, RESOLVED, DISMISSED) are session-local.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Mapping, Sequence
import streamlit as st

from frontend.utils.clock import Clock, get_current_clock
from frontend.utils.operational_intelligence import (
    OperationalSignal,
    _determine_record_data_quality,
    _extract_metric_val,
    _safe_float,
    generate_operational_signals,
)
from frontend.utils.priority import get_signal_priority, sort_signals_by_priority
from frontend.utils.responsible_analytics import RESPONSIBLE_ANALYTICS_NOTICE

_SIGNAL_LIFECYCLE_STORE_KEY = "_session_signal_lifecycle_store"
_SIGNAL_DEDUP_STORE_KEY = "_session_signal_dedup_store"

# Signal Types
SIGNAL_TYPE_WATCHLIST_MATCH = "WATCHLIST_MATCH"
SIGNAL_TYPE_THRESHOLD_BREACH = "THRESHOLD_BREACH"
SIGNAL_TYPE_RAPID_CHANGE = "RAPID_CHANGE"
SIGNAL_TYPE_SIGNIFICANT_CHANGE = "SIGNIFICANT_CHANGE"
SIGNAL_TYPE_REPEATED_HEAT = "REPEATED_HEAT"
SIGNAL_TYPE_DATA_ANOMALY = "DATA_ANOMALY"

SIGNAL_TYPE_PRECEDENCE: dict[str, int] = {
    SIGNAL_TYPE_WATCHLIST_MATCH: 6,
    SIGNAL_TYPE_THRESHOLD_BREACH: 5,
    SIGNAL_TYPE_RAPID_CHANGE: 4,
    SIGNAL_TYPE_SIGNIFICANT_CHANGE: 3,
    SIGNAL_TYPE_REPEATED_HEAT: 2,
    SIGNAL_TYPE_DATA_ANOMALY: 1,
}

# Signal Dispositions
DISPOSITION_NEW = "NEW"
DISPOSITION_ACKNOWLEDGED = "ACKNOWLEDGED"
DISPOSITION_LINKED_TO_ALERT = "LINKED_TO_ALERT"
DISPOSITION_RESOLVED = "RESOLVED"
DISPOSITION_DISMISSED = "DISMISSED"

VALID_DISPOSITIONS: frozenset[str] = frozenset({
    DISPOSITION_NEW,
    DISPOSITION_ACKNOWLEDGED,
    DISPOSITION_LINKED_TO_ALERT,
    DISPOSITION_RESOLVED,
    DISPOSITION_DISMISSED,
})


@dataclass(frozen=True)
class SignalDisposition:
    """Mutable operator state attached to an immutable OperationalSignal."""

    signal_id: str
    status: str = DISPOSITION_NEW  # NEW | ACKNOWLEDGED | LINKED_TO_ALERT | RESOLVED | DISMISSED
    updated_at: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SignalDisposition:
        return cls(
            signal_id=str(data.get("signal_id", "")),
            status=str(data.get("status", DISPOSITION_NEW)).upper(),
            updated_at=str(data.get("updated_at", "")),
            notes=str(data.get("notes", "")),
        )


def generate_signal_fingerprint(
    signal_type: str,
    analysis_id: str,
    watchlist_id: str | None = None,
    criterion_key: str | None = None,
) -> str:
    """Generate a deterministic SHA-256 identity fingerprint for a signal."""
    raw_identity = {
        "signal_type": str(signal_type).strip().upper(),
        "analysis_id": str(analysis_id).strip(),
        "watchlist_id": str(watchlist_id or "").strip(),
        "criterion_key": str(criterion_key or "").strip().lower(),
    }
    canonical_str = json.dumps(raw_identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# Disposition Store Management
# ──────────────────────────────────────────────────────────────────────────────


def _get_disposition_store() -> dict[str, dict[str, Any]]:
    if _SIGNAL_LIFECYCLE_STORE_KEY not in st.session_state:
        st.session_state[_SIGNAL_LIFECYCLE_STORE_KEY] = {}
    return st.session_state[_SIGNAL_LIFECYCLE_STORE_KEY]


def get_signal_disposition(signal_id: str) -> SignalDisposition:
    """Retrieve the disposition state of a signal (defaults to NEW)."""
    store = _get_disposition_store()
    raw = store.get(signal_id)
    if raw:
        return SignalDisposition.from_dict(raw)
    return SignalDisposition(signal_id=signal_id, status=DISPOSITION_NEW)


def update_signal_disposition(
    signal_id: str,
    status: str,
    notes: str = "",
    clock: Clock | None = None,
) -> SignalDisposition:
    """Update the operator disposition of a signal."""
    norm_status = str(status).strip().upper()
    if norm_status not in VALID_DISPOSITIONS:
        norm_status = DISPOSITION_NEW

    clk = clock or get_current_clock()
    store = _get_disposition_store()

    disp = SignalDisposition(
        signal_id=signal_id,
        status=norm_status,
        updated_at=clk.now_iso(),
        notes=notes,
    )
    store[signal_id] = disp.to_dict()
    st.session_state[_SIGNAL_LIFECYCLE_STORE_KEY] = store
    return disp


# ──────────────────────────────────────────────────────────────────────────────
# Signal Detectors
# ──────────────────────────────────────────────────────────────────────────────


def detect_watchlist_signals(
    evaluations: Sequence[Any],
    clock: Clock | None = None,
) -> list[OperationalSignal]:
    """Generate OperationalSignal events for matched Watchlist evaluations."""
    clk = clock or get_current_clock()
    signals: list[OperationalSignal] = []

    for ev in evaluations:
        e_dict = ev.to_dict() if hasattr(ev, "to_dict") else dict(ev)
        if not e_dict.get("matched"):
            continue

        wl_id = str(e_dict.get("watchlist_id", ""))
        wl_name = str(e_dict.get("watchlist_name", "Watchlist"))
        comp_id = str(e_dict.get("comparison_analysis_id", "")) or "SESSION"
        matched_crits = e_dict.get("matched_criteria", [])
        evidence_items = e_dict.get("evidence_list", [])
        dq = str(e_dict.get("data_quality", "HIGH"))

        crit_key = ":".join(sorted(matched_crits))
        fp = generate_signal_fingerprint(
            signal_type=SIGNAL_TYPE_WATCHLIST_MATCH,
            analysis_id=comp_id,
            watchlist_id=wl_id,
            criterion_key=crit_key,
        )
        sig_id = f"SIG-WL-{fp[:10]}"

        # Severity determined by temperature or delta magnitude
        delta_val = _safe_float(e_dict.get("delta"))
        obs_temp = e_dict.get("observed_values", {}).get("mean_temperature")

        severity = "ELEVATED"
        if obs_temp and obs_temp >= 40.0:
            severity = "CRITICAL"
        elif delta_val and delta_val >= 3.0:
            severity = "CRITICAL"
        elif "above_threshold_proportion" in matched_crits:
            severity = "WATCH"

        title = f"Watchlist Match: {wl_name}"
        desc = (
            f"Watchlist '{wl_name}' matched criteria ({', '.join(matched_crits)}) "
            f"on analysis {comp_id}."
        )

        sig = OperationalSignal(
            signal_id=sig_id,
            analysis_id=comp_id,
            signal_type=SIGNAL_TYPE_WATCHLIST_MATCH,
            severity=severity,
            title=title,
            description=desc,
            metric="watchlist_evaluation",
            observed_value=delta_val if delta_val is not None else obs_temp,
            threshold_value=e_dict.get("threshold_values", {}).get("mean_temperature"),
            direction="above",
            confidence="HIGH" if dq in ("HIGH", "MEDIUM") else "LOW",
            evidence=evidence_items,
            data_quality=dq,
            created_at=clk.now_iso(),
        )
        signals.append(sig)

    return signals


def detect_analysis_signals(
    records: Sequence[Any],
    clock: Clock | None = None,
) -> list[OperationalSignal]:
    """Generate pipeline signals directly from completed records with SHA-256 fingerprints."""
    clk = clock or get_current_clock()
    base_signals = generate_operational_signals(records)
    signals: list[OperationalSignal] = []

    for s in base_signals:
        sig_type = s.signal_type
        if "threshold" in sig_type.lower():
            p15_type = SIGNAL_TYPE_THRESHOLD_BREACH
        elif "increase" in sig_type.lower() or "decrease" in sig_type.lower():
            p15_type = SIGNAL_TYPE_SIGNIFICANT_CHANGE
        elif "spread" in sig_type.lower() or "proportion" in sig_type.lower():
            p15_type = SIGNAL_TYPE_RAPID_CHANGE
        elif "insufficient" in sig_type.lower() or "missing" in sig_type.lower():
            p15_type = SIGNAL_TYPE_DATA_ANOMALY
        else:
            p15_type = SIGNAL_TYPE_THRESHOLD_BREACH

        fp = generate_signal_fingerprint(
            signal_type=p15_type,
            analysis_id=s.analysis_id,
            criterion_key=s.metric or s.signal_type,
        )
        sig_id = f"SIG-{p15_type[:4]}-{fp[:10]}"

        # Re-wrap in pipeline signal
        p15_sig = OperationalSignal(
            signal_id=sig_id,
            analysis_id=s.analysis_id,
            signal_type=p15_type,
            severity=s.severity,
            title=s.title,
            description=s.description,
            metric=s.metric,
            observed_value=s.observed_value,
            threshold_value=s.threshold_value,
            direction=s.direction,
            confidence=s.confidence,
            evidence=s.evidence,
            data_quality=s.data_quality,
            created_at=clk.now_iso(),
        )
        signals.append(p15_sig)

    return signals


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline Signal Generator with Deduplication
# ──────────────────────────────────────────────────────────────────────────────


def generate_pipeline_signals(
    records: Sequence[Any],
    watchlist_evaluations: Sequence[Any] | None = None,
    clock: Clock | None = None,
) -> list[dict[str, Any]]:
    """Execute full signal pipeline with precedence sorting and idempotent deduplication."""
    clk = clock or get_current_clock()

    # 1. Detect signals
    all_raw_signals: list[OperationalSignal] = []

    if watchlist_evaluations:
        all_raw_signals.extend(detect_watchlist_signals(watchlist_evaluations, clock=clk))

    all_raw_signals.extend(detect_analysis_signals(records, clock=clk))

    # 2. Deduplicate by exact signal_id
    seen_ids: set[str] = set()
    deduped_signals: list[OperationalSignal] = []
    for s in all_raw_signals:
        if s.signal_id not in seen_ids:
            seen_ids.add(s.signal_id)
            deduped_signals.append(s)

    # 3. Sort by precedence and priority
    def sort_key(s: OperationalSignal) -> tuple[int, float]:
        prec = SIGNAL_TYPE_PRECEDENCE.get(s.signal_type, 0)
        score, _ = get_signal_priority(s)
        return (prec, score)

    sorted_signals = sorted(deduped_signals, key=sort_key, reverse=True)

    # 4. Attach disposition states
    result: list[dict[str, Any]] = []
    for s in sorted_signals:
        disp = get_signal_disposition(s.signal_id)
        d = s.to_dict()
        d["disposition"] = disp.status
        d["disposition_updated_at"] = disp.updated_at
        d["disposition_notes"] = disp.notes
        d["precedence_rank"] = SIGNAL_TYPE_PRECEDENCE.get(s.signal_type, 0)
        result.append(d)

    return result
