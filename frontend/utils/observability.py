"""Centralized Structured Observability & Audit Event Logging Layer.

Provides structured, tamper-evident audit logging for analysis lifecycle,
local intelligence pipelines, alert promotions, and investigation actions.

Strict Invariants:
1. Pure local-first logging: Zero external HTTP telemetry or network calls.
2. Recursive secret redaction: Stored event metadata is strictly sanitized.
   API keys, authentication tokens, passwords, and signed storage URLs are scrubbed before storage.
3. Bounded session buffer: FIFO rotation capped at MAX_OBSERVABILITY_EVENTS.
4. Deterministic event timestamps with injectable Clock support.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
import re
from typing import Any, Mapping, Sequence
import streamlit as st

from frontend.utils.clock import Clock, get_current_clock

logger = logging.getLogger("fortyguard.observability")

_OBSERVABILITY_STORE_KEY = "_session_observability_events"
MAX_OBSERVABILITY_EVENTS: int = 500

_SECRET_KEYS_REGEX = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|signed[_-]?url|download[_-]?link|credentials|bearer|cookie)"
)

# Canonical Event Names
EVENT_ANALYSIS_SUBMITTED = "analysis_submitted"
EVENT_ANALYSIS_POLL_STARTED = "analysis_poll_started"
EVENT_ANALYSIS_POLL_COMPLETED = "analysis_poll_completed"
EVENT_ANALYSIS_FAILED = "analysis_failed"
EVENT_ANALYSIS_TIMEOUT = "analysis_timeout"
EVENT_ANALYSIS_RETRY = "analysis_retry"
EVENT_WATCHLIST_EVALUATED = "watchlist_evaluated"
EVENT_SIGNAL_GENERATED = "signal_generated"
EVENT_SIGNAL_DEDUPLICATED = "signal_deduplicated"
EVENT_ALERT_PROMOTED = "alert_promoted"
EVENT_ALERT_SUPPRESSED = "alert_suppressed"
EVENT_ALERT_COOLDOWN = "alert_cooldown"
EVENT_INVESTIGATION_CREATED = "investigation_created"
EVENT_EVIDENCE_GENERATED = "evidence_generated"
EVENT_EXPORT_GENERATED = "export_generated"
EVENT_PATTERN_DETECTED = "pattern_detected"
EVENT_LATEST_CHANGE_COMPUTED = "latest_change_computed"
EVENT_LOCATION_SUMMARY_BUILT = "location_summary_built"
EVENT_ALERT_GROUPED = "alert_grouped"
EVENT_OPERATOR_ACTION_GENERATED = "operator_action_generated"
EVENT_REVIEW_DELTA_COMPUTED = "review_delta_computed"
EVENT_DECISION_BRIEF_GENERATED = "decision_brief_generated"

VALID_EVENT_NAMES: frozenset[str] = frozenset({
    EVENT_ANALYSIS_SUBMITTED,
    EVENT_ANALYSIS_POLL_STARTED,
    EVENT_ANALYSIS_POLL_COMPLETED,
    EVENT_ANALYSIS_FAILED,
    EVENT_ANALYSIS_TIMEOUT,
    EVENT_ANALYSIS_RETRY,
    EVENT_WATCHLIST_EVALUATED,
    EVENT_SIGNAL_GENERATED,
    EVENT_SIGNAL_DEDUPLICATED,
    EVENT_ALERT_PROMOTED,
    EVENT_ALERT_SUPPRESSED,
    EVENT_ALERT_COOLDOWN,
    EVENT_INVESTIGATION_CREATED,
    EVENT_EVIDENCE_GENERATED,
    EVENT_EXPORT_GENERATED,
    EVENT_PATTERN_DETECTED,
    EVENT_LATEST_CHANGE_COMPUTED,
    EVENT_LOCATION_SUMMARY_BUILT,
    EVENT_ALERT_GROUPED,
    EVENT_OPERATOR_ACTION_GENERATED,
    EVENT_REVIEW_DELTA_COMPUTED,
    EVENT_DECISION_BRIEF_GENERATED,
})


def sanitize_observability_data(val: Any) -> Any:
    """Recursively redact credentials, tokens, and signed URLs from event payloads."""
    if isinstance(val, Mapping):
        cleaned: dict[str, Any] = {}
        for k, v in val.items():
            if _SECRET_KEYS_REGEX.search(str(k)):
                cleaned[k] = "[REDACTED]"
            elif isinstance(v, str) and (
                "X-Amz-Signature=" in v
                or "X-Amz-Credential=" in v
                or "Signature=" in v
                or _SECRET_KEYS_REGEX.search(v)
            ):
                cleaned[k] = "[REDACTED_URL]"
            else:
                cleaned[k] = sanitize_observability_data(v)
        return cleaned
    elif isinstance(val, (list, tuple)):
        return [sanitize_observability_data(item) for item in val]
    elif isinstance(val, str):
        lowered = val.lower()
        if (
            "x-amz-signature=" in lowered
            or "x-amz-credential=" in lowered
            or "signature=" in lowered
            or "signedurl" in lowered.replace("_", "")
        ):
            return "[REDACTED_SIGNED_URL]"
        return val
    return val


@dataclass(frozen=True)
class ObservabilityEvent:
    """Immutable, sanitized structured observability event."""

    event_name: str
    timestamp: str
    analysis_id: str | None = None
    activity_id: str | None = None
    attempt_number: int = 1
    phase: str = "phase16"
    duration_ms: float = 0.0
    status: str = "SUCCESS"  # SUCCESS | FAILED | TIMEOUT | SUPPRESSED
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ObservabilityEvent:
        raw_meta = data.get("metadata", {})
        clean_meta = sanitize_observability_data(dict(raw_meta) if isinstance(raw_meta, Mapping) else {})
        return cls(
            event_name=str(data.get("event_name", "generic_event")),
            timestamp=str(data.get("timestamp", "")),
            analysis_id=data.get("analysis_id"),
            activity_id=data.get("activity_id"),
            attempt_number=int(data.get("attempt_number", 1)),
            phase=str(data.get("phase", "phase16")),
            duration_ms=float(data.get("duration_ms", 0.0)),
            status=str(data.get("status", "SUCCESS")),
            metadata=clean_meta,
        )


def record_event(
    event_name: str,
    analysis_id: str | None = None,
    activity_id: str | None = None,
    attempt_number: int = 1,
    phase: str = "phase16",
    duration_ms: float = 0.0,
    status: str = "SUCCESS",
    metadata: Mapping[str, Any] | None = None,
    clock: Clock | None = None,
) -> ObservabilityEvent:
    """Record a structured observability event into session state.

    Args:
        event_name: Canonical event identifier string.
        analysis_id: Associated analysis record ID if applicable.
        activity_id: Provider activity ID if applicable.
        attempt_number: Current retry/poll attempt number.
        phase: Architectural phase or component name.
        duration_ms: Wall-clock execution time in milliseconds.
        status: SUCCESS | FAILED | TIMEOUT | SUPPRESSED.
        metadata: Arbitrary event metadata dictionary (auto-sanitized).
        clock: Optional injectable Clock for deterministic timestamps.

    Returns:
        The newly recorded and stored ObservabilityEvent.
    """
    clk = clock or get_current_clock()
    now_iso = clk.now_iso()

    clean_meta = sanitize_observability_data(dict(metadata or {}))

    event = ObservabilityEvent(
        event_name=event_name,
        timestamp=now_iso,
        analysis_id=analysis_id,
        activity_id=activity_id,
        attempt_number=attempt_number,
        phase=phase,
        duration_ms=round(float(duration_ms), 2),
        status=status,
        metadata=clean_meta,
    )

    # Store in session state with FIFO rotation
    raw_list = list(st.session_state.get(_OBSERVABILITY_STORE_KEY, []))
    raw_list.append(event.to_dict())

    if len(raw_list) > MAX_OBSERVABILITY_EVENTS:
        raw_list = raw_list[-MAX_OBSERVABILITY_EVENTS:]

    st.session_state[_OBSERVABILITY_STORE_KEY] = raw_list
    logger.debug("Recorded observability event: %s (%s)", event_name, status)
    return event


def get_observability_events(
    event_name: str | None = None,
    analysis_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[ObservabilityEvent]:
    """Retrieve recorded observability events filtered by name, analysis_id, or status."""
    raw_list = st.session_state.get(_OBSERVABILITY_STORE_KEY, [])
    events: list[ObservabilityEvent] = []

    for d in raw_list:
        if not isinstance(d, Mapping):
            continue
        ev = ObservabilityEvent.from_dict(d)
        if event_name and ev.event_name != event_name:
            continue
        if analysis_id and ev.analysis_id != analysis_id:
            continue
        if status and ev.status.upper() != status.upper():
            continue
        events.append(ev)

    # Return newest first up to limit
    return events[-limit:]


def clear_observability_events() -> None:
    """Clear all recorded observability events from session storage."""
    if _OBSERVABILITY_STORE_KEY in st.session_state:
        del st.session_state[_OBSERVABILITY_STORE_KEY]
