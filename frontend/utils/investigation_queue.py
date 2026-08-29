"""Session-Local Investigation Queue and Workflow Engine.

Manages prioritized investigation items in st.session_state with immutable audit
events, assignment tracking, structured analyst notes CRUD, and evidence bundles.

Strict Invariants:
1. Session-local storage only in st.session_state (zero DB, zero external disk/cloud).
2. Maximum 100 queue items.
3. Supported statuses: OPEN, IN_REVIEW, RESOLVED, DISMISSED.
4. Prevents duplicate active queue items for the same analysis and signal.
5. All lifecycle actions record immutable InvestigationEvent audit records.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Mapping, Sequence
import streamlit as st

from frontend.utils.clock import Clock, get_current_clock
from frontend.utils.evidence import EvidenceBundle, build_evidence_bundle
from frontend.utils.operational_intelligence import (
    _determine_record_data_quality,
    _extract_metric_val,
    _safe_float,
)

_QUEUE_STORE_KEY = "_session_investigation_queue"
_QUEUE_COUNTER_KEY = "_session_investigation_counter"

MAX_INVESTIGATION_QUEUE_ITEMS: int = 100

STATUS_OPEN = "OPEN"
STATUS_IN_REVIEW = "IN_REVIEW"
STATUS_RESOLVED = "RESOLVED"
STATUS_DISMISSED = "DISMISSED"

VALID_QUEUE_STATUSES: frozenset[str] = frozenset({
    STATUS_OPEN,
    STATUS_IN_REVIEW,
    STATUS_RESOLVED,
    STATUS_DISMISSED,
})

PRIORITY_RANK: dict[str, int] = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
}


@dataclass(frozen=True)
class InvestigationEvent:
    """Immutable audit trail event within an investigation."""

    event_id: str
    event_type: str  # "CREATED" | "STATUS_CHANGE" | "NOTE_ADDED" | "ASSIGNED" | "EVIDENCE_REFRESHED"
    timestamp: str
    actor: str = "Analyst"
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> InvestigationEvent:
        return cls(
            event_id=str(data.get("event_id", "")),
            event_type=str(data.get("event_type", "EVENT")),
            timestamp=str(data.get("timestamp", "")),
            actor=str(data.get("actor", "Analyst")),
            details=str(data.get("details", "")),
        )


@dataclass
class InvestigationItem:
    """Represents a prioritized analysis investigation item."""

    queue_id: str
    analysis_id: str
    signal_id: str | None = None
    alert_id: str | None = None
    priority: str = "Medium"  # "Critical" | "High" | "Medium" | "Low"
    reason: str = ""
    location: str = "Analysis Area"
    analysis_type: str = "heatmap"
    status: str = STATUS_OPEN  # "OPEN" | "IN_REVIEW" | "RESOLVED" | "DISMISSED"
    assigned_to: str = "Unassigned"
    notes: str = ""
    notes_list: list[dict[str, str]] = field(default_factory=list)
    events: list[InvestigationEvent] = field(default_factory=list)
    evidence_bundle: dict[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""
    metric: str | None = None
    observed_value: float | None = None
    threshold_value: float | None = None
    data_quality: str | None = None
    delta: float | None = None
    percent_delta: float | None = None
    watchlist_id: str | None = None
    criterion_key: str | None = None
    signal_type: str | None = None
    source_signal: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["events"] = [e.to_dict() if isinstance(e, InvestigationEvent) else dict(e) for e in self.events]
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> InvestigationItem:
        raw_events = data.get("events", [])
        events = [InvestigationEvent.from_dict(e) if isinstance(e, Mapping) else e for e in raw_events]
        raw_notes_list = data.get("notes_list", [])

        return cls(
            queue_id=str(data.get("queue_id", "")),
            analysis_id=str(data.get("analysis_id", "")),
            signal_id=str(data["signal_id"]) if data.get("signal_id") else None,
            alert_id=str(data["alert_id"]) if data.get("alert_id") else None,
            priority=str(data.get("priority", "Medium")).title(),
            reason=str(data.get("reason", "")),
            location=str(data.get("location", "Analysis Area")),
            analysis_type=str(data.get("analysis_type", "heatmap")),
            status=str(data.get("status", STATUS_OPEN)).upper(),
            assigned_to=str(data.get("assigned_to", "Unassigned")),
            notes=str(data.get("notes", "")),
            notes_list=list(raw_notes_list),
            events=events,
            evidence_bundle=data.get("evidence_bundle"),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            metric=data.get("metric"),
            observed_value=_safe_float(data.get("observed_value")),
            threshold_value=_safe_float(data.get("threshold_value")),
            data_quality=str(data["data_quality"]) if data.get("data_quality") else None,
            delta=_safe_float(data.get("delta")),
            percent_delta=_safe_float(data.get("percent_delta")),
            watchlist_id=data.get("watchlist_id"),
            criterion_key=data.get("criterion_key"),
            signal_type=data.get("signal_type"),
            source_signal=dict(data["source_signal"]) if isinstance(data.get("source_signal"), Mapping) else None,
        )


def _get_raw_queue() -> list[dict[str, Any]]:
    if _QUEUE_STORE_KEY not in st.session_state:
        st.session_state[_QUEUE_STORE_KEY] = []
    return st.session_state[_QUEUE_STORE_KEY]


def generate_queue_id(clock: Clock | None = None) -> str:
    """Generate a collision-safe session queue ID."""
    clk = clock or get_current_clock()
    if _QUEUE_COUNTER_KEY not in st.session_state:
        st.session_state[_QUEUE_COUNTER_KEY] = 0
    st.session_state[_QUEUE_COUNTER_KEY] += 1
    return f"Q-{clk.now().strftime('%Y%m%d%H%M%S')}-{st.session_state[_QUEUE_COUNTER_KEY]:03d}"


def get_investigation_queue() -> list[InvestigationItem]:
    """Retrieve all investigation items from session state."""
    raw = _get_raw_queue()
    return [InvestigationItem.from_dict(d) for d in raw if isinstance(d, Mapping)]


def get_investigation_item(queue_id: str) -> InvestigationItem | None:
    """Retrieve a single investigation item by queue_id."""
    for item in get_investigation_queue():
        if item.queue_id == queue_id:
            return item
    return None


def add_to_investigation_queue(
    analysis_id: str,
    signal_id: str | None = None,
    alert_id: str | None = None,
    priority: str = "Medium",
    reason: str = "",
    location: str = "Analysis Area",
    analysis_type: str = "heatmap",
    notes: str = "",
    clock: Clock | None = None,
    metric: str | None = None,
    observed_value: float | None = None,
    threshold_value: float | None = None,
    data_quality: str | None = None,
    delta: float | None = None,
    percent_delta: float | None = None,
    watchlist_id: str | None = None,
    criterion_key: str | None = None,
    signal_type: str | None = None,
    source_signal: Any | None = None,
    evidence_bundle: Any | None = None,
) -> tuple[bool, str | None, InvestigationItem | None]:
    """Add an analysis, signal, or alert to the investigation queue while preserving exact evidence."""
    if not analysis_id:
        return False, "Analysis ID is required.", None

    clk = clock or get_current_clock()
    now_iso = clk.now_iso()
    current = get_investigation_queue()

    if len(current) >= MAX_INVESTIGATION_QUEUE_ITEMS:
        return False, f"Investigation queue has reached maximum capacity ({MAX_INVESTIGATION_QUEUE_ITEMS} items).", None

    src_sig_dict: dict[str, Any] | None = None
    if source_signal is not None:
        src_sig_dict = source_signal.to_dict() if hasattr(source_signal, "to_dict") else dict(source_signal)
        signal_id = signal_id or src_sig_dict.get("signal_id")
        alert_id = alert_id or src_sig_dict.get("alert_id")
        signal_type = signal_type or src_sig_dict.get("signal_type")
        metric = metric or src_sig_dict.get("metric")
        if observed_value is None and src_sig_dict.get("observed_value") is not None:
            observed_value = _safe_float(src_sig_dict.get("observed_value"))
        if threshold_value is None and src_sig_dict.get("threshold_value") is not None:
            threshold_value = _safe_float(src_sig_dict.get("threshold_value"))
        data_quality = data_quality or src_sig_dict.get("data_quality")
        if delta is None and src_sig_dict.get("delta") is not None:
            delta = _safe_float(src_sig_dict.get("delta"))
        if percent_delta is None and src_sig_dict.get("percent_delta") is not None:
            percent_delta = _safe_float(src_sig_dict.get("percent_delta"))
        watchlist_id = watchlist_id or src_sig_dict.get("watchlist_id")
        criterion_key = criterion_key or src_sig_dict.get("criterion_key")
        if not reason:
            reason = str(src_sig_dict.get("title") or src_sig_dict.get("reason") or src_sig_dict.get("description") or "")
        if location == "Analysis Area" and src_sig_dict.get("location"):
            location = str(src_sig_dict["location"])
    else:
        # Auto-resolve from session AnalysisRecord and detected operational signals
        try:
            from frontend.utils.analysis_history import get_analysis_record
            rec = get_analysis_record(analysis_id)
            if rec:
                if location == "Analysis Area" and rec.location_label:
                    location = rec.location_label
                if analysis_type == "heatmap" and rec.analysis_type:
                    analysis_type = rec.analysis_type

                from frontend.utils.operational_intelligence import generate_operational_signals
                sigs = generate_operational_signals([rec])
                matching_sig = None
                if signal_id:
                    for s in sigs:
                        if s.signal_id == signal_id:
                            matching_sig = s
                            break
                if not matching_sig and sigs:
                    matching_sig = sigs[0]

                if matching_sig:
                    src_sig_dict = matching_sig.to_dict()
                    signal_id = signal_id or matching_sig.signal_id
                    signal_type = signal_type or matching_sig.signal_type
                    metric = metric or matching_sig.metric
                    if observed_value is None:
                        observed_value = matching_sig.observed_value
                    if threshold_value is None:
                        threshold_value = matching_sig.threshold_value
                    data_quality = data_quality or matching_sig.data_quality
                    if not reason:
                        reason = matching_sig.title
                else:
                    if observed_value is None:
                        if rec.observed_temperature is not None:
                            observed_value = rec.observed_temperature
                            metric = metric or "observed_temperature"
                        elif isinstance(rec.metrics, Mapping) and rec.metrics.get("mean_temp") is not None:
                            observed_value = _safe_float(rec.metrics.get("mean_temp"))
                            metric = metric or "mean_temperature"
                    data_quality = data_quality or _determine_record_data_quality(rec.to_dict())
        except Exception:
            pass

    # Check for active duplicates
    for item in current:
        if item.status in (STATUS_OPEN, STATUS_IN_REVIEW):
            if item.analysis_id == analysis_id and item.signal_id == signal_id and item.alert_id == alert_id:
                return False, f"Analysis '{analysis_id}' is already present in the active investigation queue.", None

    queue_id = generate_queue_id(clock=clk)
    create_event = InvestigationEvent(
        event_id=f"EVT-{hashlib.sha256(f'{queue_id}_CREATED'.encode()).hexdigest()[:8]}",
        event_type="CREATED",
        timestamp=now_iso,
        actor="System",
        details=f"Investigation item created with {priority} priority.",
    )

    initial_notes_list = []
    if notes.strip():
        initial_notes_list.append({
            "note_id": "NOTE-001",
            "author": "Analyst",
            "text": notes.strip(),
            "timestamp": now_iso,
        })

    # Prepare EvidenceBundle
    eb_dict: dict[str, Any] | None = None
    if evidence_bundle is not None:
        eb_dict = evidence_bundle.to_dict() if hasattr(evidence_bundle, "to_dict") else dict(evidence_bundle)
    elif src_sig_dict is not None or (observed_value is not None or threshold_value is not None):
        target_obj = src_sig_dict.copy() if src_sig_dict else {
            "signal_id": signal_id or f"SIG-{analysis_id}",
            "analysis_id": analysis_id,
            "title": reason,
            "metric": metric,
            "observed_value": observed_value,
            "threshold_value": threshold_value,
            "data_quality": data_quality or "HIGH",
        }
        eb = build_evidence_bundle(target_obj, clock=clk)
        eb_dict = eb.to_dict()

    new_item = InvestigationItem(
        queue_id=queue_id,
        analysis_id=analysis_id,
        signal_id=signal_id,
        alert_id=alert_id,
        priority=priority.title(),
        reason=reason,
        location=location,
        analysis_type=analysis_type,
        status=STATUS_OPEN,
        assigned_to="Unassigned",
        notes=notes,
        notes_list=initial_notes_list,
        events=[create_event],
        evidence_bundle=eb_dict,
        created_at=now_iso,
        updated_at=now_iso,
        metric=metric,
        observed_value=observed_value,
        threshold_value=threshold_value,
        data_quality=data_quality,
        delta=delta,
        percent_delta=percent_delta,
        watchlist_id=watchlist_id,
        criterion_key=criterion_key,
        signal_type=signal_type,
        source_signal=src_sig_dict,
    )

    current.append(new_item)
    st.session_state[_QUEUE_STORE_KEY] = [item.to_dict() for item in current]
    return True, None, new_item


def remove_from_investigation_queue(queue_id: str) -> tuple[bool, str | None]:
    """Permanently remove an item from the investigation queue."""
    current = get_investigation_queue()
    updated = [item for item in current if item.queue_id != queue_id]
    if len(updated) == len(current):
        return False, f"Queue item '{queue_id}' not found."

    st.session_state[_QUEUE_STORE_KEY] = [item.to_dict() for item in updated]
    return True, None


def mark_in_review(
    queue_id: str,
    notes: str | None = None,
    actor: str = "Analyst",
    clock: Clock | None = None,
) -> tuple[bool, str | None]:
    """Set queue item status to IN_REVIEW with audit event."""
    clk = clock or get_current_clock()
    now_iso = clk.now_iso()
    current = get_investigation_queue()
    found = False

    for item in current:
        if item.queue_id == queue_id:
            item.status = STATUS_IN_REVIEW
            item.updated_at = now_iso
            if notes is not None:
                item.notes = notes

            event = InvestigationEvent(
                event_id=f"EVT-{hashlib.sha256(f'{queue_id}_{now_iso}_IN_REVIEW'.encode()).hexdigest()[:8]}",
                event_type="STATUS_CHANGE",
                timestamp=now_iso,
                actor=actor,
                details="Status updated to IN_REVIEW.",
            )
            item.events.append(event)
            found = True
            break

    if not found:
        return False, f"Queue item '{queue_id}' not found."

    st.session_state[_QUEUE_STORE_KEY] = [item.to_dict() for item in current]
    return True, None


def mark_resolved(
    queue_id: str,
    notes: str | None = None,
    actor: str = "Analyst",
    clock: Clock | None = None,
) -> tuple[bool, str | None]:
    """Set queue item status to RESOLVED with audit event."""
    clk = clock or get_current_clock()
    now_iso = clk.now_iso()
    current = get_investigation_queue()
    found = False

    for item in current:
        if item.queue_id == queue_id:
            item.status = STATUS_RESOLVED
            item.updated_at = now_iso
            if notes is not None:
                item.notes = notes

            event = InvestigationEvent(
                event_id=f"EVT-{hashlib.sha256(f'{queue_id}_{now_iso}_RESOLVED'.encode()).hexdigest()[:8]}",
                event_type="STATUS_CHANGE",
                timestamp=now_iso,
                actor=actor,
                details="Investigation marked as RESOLVED.",
            )
            item.events.append(event)
            found = True
            break

    if not found:
        return False, f"Queue item '{queue_id}' not found."

    st.session_state[_QUEUE_STORE_KEY] = [item.to_dict() for item in current]
    return True, None


def add_note_to_investigation(
    queue_id: str,
    note_text: str,
    author: str = "Analyst",
    clock: Clock | None = None,
) -> tuple[bool, str | None]:
    """Add a structured timestamped note to an investigation item."""
    if not note_text.strip():
        return False, "Note text cannot be empty."

    clk = clock or get_current_clock()
    now_iso = clk.now_iso()
    current = get_investigation_queue()
    found = False

    for item in current:
        if item.queue_id == queue_id:
            note_obj = {
                "note_id": f"NOTE-{len(item.notes_list) + 1:03d}",
                "author": author,
                "text": note_text.strip(),
                "timestamp": now_iso,
            }
            item.notes_list.append(note_obj)
            item.updated_at = now_iso

            event = InvestigationEvent(
                event_id=f"EVT-{hashlib.sha256(f'{queue_id}_{now_iso}_NOTE'.encode()).hexdigest()[:8]}",
                event_type="NOTE_ADDED",
                timestamp=now_iso,
                actor=author,
                details=f"Added analyst note: {note_text.strip()[:40]}...",
            )
            item.events.append(event)
            found = True
            break

    if not found:
        return False, f"Queue item '{queue_id}' not found."

    st.session_state[_QUEUE_STORE_KEY] = [item.to_dict() for item in current]
    return True, None


def assign_investigation(
    queue_id: str,
    assignee: str,
    actor: str = "Lead Analyst",
    clock: Clock | None = None,
) -> tuple[bool, str | None]:
    """Assign an investigation item to an analyst."""
    clean_assignee = assignee.strip() or "Unassigned"
    clk = clock or get_current_clock()
    now_iso = clk.now_iso()
    current = get_investigation_queue()
    found = False

    for item in current:
        if item.queue_id == queue_id:
            item.assigned_to = clean_assignee
            item.updated_at = now_iso

            event = InvestigationEvent(
                event_id=f"EVT-{hashlib.sha256(f'{queue_id}_{now_iso}_ASSIGN'.encode()).hexdigest()[:8]}",
                event_type="ASSIGNED",
                timestamp=now_iso,
                actor=actor,
                details=f"Assigned to {clean_assignee}.",
            )
            item.events.append(event)
            found = True
            break

    if not found:
        return False, f"Queue item '{queue_id}' not found."

    st.session_state[_QUEUE_STORE_KEY] = [item.to_dict() for item in current]
    return True, None


def attach_evidence_bundle(
    queue_id: str,
    bundle: EvidenceBundle | dict[str, Any],
    clock: Clock | None = None,
) -> bool:
    """Attach or update the EvidenceBundle on an investigation item."""
    bundle_dict = bundle.to_dict() if isinstance(bundle, EvidenceBundle) else dict(bundle)
    clk = clock or get_current_clock()
    now_iso = clk.now_iso()
    current = get_investigation_queue()

    for item in current:
        if item.queue_id == queue_id:
            item.evidence_bundle = bundle_dict
            item.updated_at = now_iso
            event = InvestigationEvent(
                event_id=f"EVT-{hashlib.sha256(f'{queue_id}_{now_iso}_EVD'.encode()).hexdigest()[:8]}",
                event_type="EVIDENCE_REFRESHED",
                timestamp=now_iso,
                actor="System",
                details=f"Attached evidence bundle {bundle_dict.get('evidence_id')}.",
            )
            item.events.append(event)
            st.session_state[_QUEUE_STORE_KEY] = [i.to_dict() for i in current]
            return True
    return False


def sync_investigation_queue_with_signals_and_alerts(
    signals: Sequence[Any],
    alerts: Sequence[Any],
    clock: Clock | None = None,
) -> list[InvestigationItem]:
    """Synchronize investigation queue by promoting Critical/High signals and alerts."""
    clk = clock or get_current_clock()

    # Process High/Critical Alerts
    for a in alerts:
        a_dict = a.to_dict() if hasattr(a, "to_dict") else dict(a)
        tier = str(a_dict.get("priority_tier", "Medium")).title()
        if tier in ("Critical", "High"):
            add_to_investigation_queue(
                analysis_id=str(a_dict.get("analysis_id", "")),
                alert_id=str(a_dict.get("alert_id", "")),
                signal_id=str(a_dict.get("signal_id", "")) if a_dict.get("signal_id") else None,
                priority=tier,
                reason=str(a_dict.get("promotion_reason") or a_dict.get("policy_name", "Alert Breach")),
                location=str(a_dict.get("location", "Analysis Area")),
                source_signal=a_dict,
                clock=clk,
            )

    return get_investigation_queue()


def list_open_queue() -> list[InvestigationItem]:
    """List active queue items (OPEN and IN_REVIEW) sorted by priority descending."""
    current = get_investigation_queue()
    active = [item for item in current if item.status in (STATUS_OPEN, STATUS_IN_REVIEW)]

    def _sort_key(item: InvestigationItem) -> tuple[int, str]:
        rank = PRIORITY_RANK.get(item.priority.upper(), 0)
        return (-rank, item.created_at)

    active.sort(key=_sort_key)
    return active


def clear_investigation_queue() -> None:
    """Clear all investigation queue items from session state."""
    st.session_state[_QUEUE_STORE_KEY] = []
    st.session_state[_QUEUE_COUNTER_KEY] = 0
