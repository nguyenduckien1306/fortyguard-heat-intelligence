"""Session-Local Review Delta Engine (Phase 17).

Tracks a session-local "last reviewed" marker and computes what changed
since the operator last looked. Purely session-local, no persistence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from frontend.utils.clock import Clock, get_current_clock, _parse_iso_datetime


@dataclass(frozen=True)
class ReviewDelta:
    """Immutable summary of what changed since the operator's last review."""

    last_review_timestamp: str | None
    current_timestamp: str
    new_analyses: list[str]
    new_signals: list[str]
    new_alerts: list[str]
    alerts_changed_state: list[dict[str, str]]  # {"alert_id": ..., "old": ..., "new": ...}
    new_investigations: list[str]
    investigations_resolved: list[str]
    watchlists_newly_triggered: list[str]
    has_changes: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return dict(obj.to_dict())
    if isinstance(obj, Mapping):
        return dict(obj)
    return {}


def _get_timestamp(d: dict) -> str | None:
    ts = d.get("created_at") or d.get("timestamp") or d.get("date")
    if ts and isinstance(ts, str):
        return ts
    return None


def _is_after(ts: str, marker: str) -> bool:
    """Check if ts is after marker, using ISO comparison."""
    try:
        ts_dt = _parse_iso_datetime(ts)
        marker_dt = _parse_iso_datetime(marker)
        # Normalize timezone
        if ts_dt.tzinfo is not None and marker_dt.tzinfo is None:
            from datetime import timezone
            marker_dt = marker_dt.replace(tzinfo=timezone.utc)
        elif ts_dt.tzinfo is None and marker_dt.tzinfo is not None:
            from datetime import timezone
            ts_dt = ts_dt.replace(tzinfo=timezone.utc)
        return ts_dt > marker_dt
    except Exception:
        return ts > marker  # Lexicographic fallback


def compute_review_delta(
    last_review_timestamp: str | None,
    records: Sequence[Any] | None = None,
    signals: Sequence[Any] | None = None,
    alerts: Sequence[Any] | None = None,
    previous_alert_states: dict[str, str] | None = None,
    queue_items: Sequence[Any] | None = None,
    previous_queue_states: dict[str, str] | None = None,
    watchlist_evaluations: Sequence[Any] | None = None,
    clock: Clock | None = None,
) -> ReviewDelta:
    """Compute what changed since the operator's last review timestamp."""
    clk = clock or get_current_clock()
    now_iso = clk.now_iso()

    rec_list = [_get_dict(r) for r in (records or [])]
    sig_list = [_get_dict(s) for s in (signals or [])]
    alert_list = [_get_dict(a) for a in (alerts or [])]
    queue_list = [_get_dict(q) for q in (queue_items or [])]
    wl_eval_list = [_get_dict(w) for w in (watchlist_evaluations or [])]
    prev_alert = previous_alert_states or {}
    prev_queue = previous_queue_states or {}

    # If no last review, everything is new
    if not last_review_timestamp:
        new_analyses = [str(r.get("analysis_id", "UNKNOWN")) for r in rec_list]
        new_signals = [str(s.get("signal_id", "UNKNOWN")) for s in sig_list]
        new_alerts = [str(a.get("alert_id", "UNKNOWN")) for a in alert_list]
        new_investigations = [str(q.get("queue_id", q.get("item_id", "UNKNOWN"))) for q in queue_list]
        wl_triggered = [str(w.get("watchlist_id", "UNKNOWN")) for w in wl_eval_list if w.get("matched") or w.get("status") == "TRIGGERED"]

        has_changes = bool(new_analyses or new_signals or new_alerts or new_investigations or wl_triggered)

        return ReviewDelta(
            last_review_timestamp=None,
            current_timestamp=now_iso,
            new_analyses=new_analyses,
            new_signals=new_signals,
            new_alerts=new_alerts,
            alerts_changed_state=[],
            new_investigations=new_investigations,
            investigations_resolved=[],
            watchlists_newly_triggered=wl_triggered,
            has_changes=has_changes,
        )

    marker = last_review_timestamp

    # New analyses since marker
    new_analyses = []
    for r in rec_list:
        ts = _get_timestamp(r)
        if ts and _is_after(ts, marker):
            new_analyses.append(str(r.get("analysis_id", "UNKNOWN")))

    # New signals since marker
    new_signals = []
    for s in sig_list:
        ts = _get_timestamp(s)
        if ts and _is_after(ts, marker):
            new_signals.append(str(s.get("signal_id", "UNKNOWN")))

    # New alerts since marker
    new_alerts = []
    for a in alert_list:
        ts = _get_timestamp(a)
        if ts and _is_after(ts, marker):
            new_alerts.append(str(a.get("alert_id", "UNKNOWN")))

    # Alerts that changed state
    alerts_changed = []
    for a in alert_list:
        aid = str(a.get("alert_id", ""))
        current_status = str(a.get("status", "ACTIVE")).upper()
        old_status = prev_alert.get(aid, "").upper()
        if old_status and old_status != current_status:
            alerts_changed.append({"alert_id": aid, "old": old_status, "new": current_status})

    # New investigations
    new_investigations = []
    for q in queue_list:
        ts = _get_timestamp(q)
        if ts and _is_after(ts, marker):
            new_investigations.append(str(q.get("queue_id", q.get("item_id", "UNKNOWN"))))

    # Investigations resolved
    investigations_resolved = []
    for q in queue_list:
        qid = str(q.get("queue_id", q.get("item_id", "")))
        current_status = str(q.get("status", "OPEN")).upper()
        old_status = prev_queue.get(qid, "").upper()
        if current_status in ("RESOLVED", "CLOSED") and old_status and old_status not in ("RESOLVED", "CLOSED"):
            investigations_resolved.append(qid)

    # Watchlists newly triggered
    wl_triggered = []
    for w in wl_eval_list:
        if w.get("matched") or w.get("status") == "TRIGGERED":
            ts = _get_timestamp(w)
            if ts and _is_after(ts, marker):
                wl_triggered.append(str(w.get("watchlist_id", "UNKNOWN")))

    has_changes = bool(new_analyses or new_signals or new_alerts or alerts_changed
                       or new_investigations or investigations_resolved or wl_triggered)

    return ReviewDelta(
        last_review_timestamp=marker,
        current_timestamp=now_iso,
        new_analyses=new_analyses,
        new_signals=new_signals,
        new_alerts=new_alerts,
        alerts_changed_state=alerts_changed,
        new_investigations=new_investigations,
        investigations_resolved=investigations_resolved,
        watchlists_newly_triggered=wl_triggered,
        has_changes=has_changes,
    )
