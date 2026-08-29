"""Session-local history tracking and workspace audit for analyses.

Maintains an in-memory session audit of analyses created during the current
browser session. Strictly preserves the security boundary: never stores API keys,
authorization tokens, or signed storage URLs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
import streamlit as st

_HISTORY_KEY = "_session_analysis_history"
_MAX_HISTORY_ITEMS = 20


def get_session_history() -> list[dict[str, Any]]:
    """Retrieve the session-local list of analyses."""
    if _HISTORY_KEY not in st.session_state:
        st.session_state[_HISTORY_KEY] = []
    return list(st.session_state[_HISTORY_KEY])


def get_analysis_by_id(activity_id: str) -> dict[str, Any] | None:
    """Retrieve a specific analysis by its activity ID."""
    if not activity_id:
        return None
    for entry in get_session_history():
        if entry.get("activity_id") == activity_id:
            return dict(entry)
    return None


def _sanitize_dict_for_storage(data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Strip any secret or signed URL fields before saving to session state."""
    if not data or not isinstance(data, Mapping):
        return {}
    sanitized: dict[str, Any] = {}
    for k, v in data.items():
        if k in ("download_link", "api_key", "headers", "token", "Authorization"):
            continue
        if isinstance(v, Mapping):
            sanitized[k] = _sanitize_dict_for_storage(v)
        else:
            sanitized[k] = v
    return sanitized


def record_session_analysis(
    analysis_type: str,
    activity_id: str,
    label: str,
    status: str,
    summary: str = "",
    request_params: dict[str, Any] | None = None,
    metrics_summary: dict[str, Any] | None = None,
    result_cached: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Record or update an analysis run in the session history.

    Never stores sensitive information (API keys, authorization headers, or signed S3 URLs).
    """
    if not activity_id:
        return

    history = get_session_history()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sanitized_req = _sanitize_dict_for_storage(request_params)
    sanitized_metrics = _sanitize_dict_for_storage(metrics_summary)
    sanitized_result = _sanitize_dict_for_storage(result_cached)
    sanitized_details = _sanitize_dict_for_storage(details)

    # Check if entry already exists (update rather than duplicating)
    for entry in history:
        if entry.get("activity_id") == activity_id:
            entry["status"] = status
            if summary:
                entry["summary"] = summary
            if sanitized_req:
                entry["request_params"] = sanitized_req
            if sanitized_metrics:
                entry["metrics_summary"] = sanitized_metrics
            if sanitized_result:
                entry["result_cached"] = sanitized_result
            if sanitized_details:
                entry["details"] = sanitized_details
            entry["updated_at"] = now_str
            st.session_state[_HISTORY_KEY] = history
            return

    new_entry = {
        "analysis_type": analysis_type,
        "activity_id": activity_id,
        "label": label or f"{analysis_type} Analysis",
        "status": status,
        "summary": summary,
        "created_at": now_str,
        "updated_at": now_str,
        "request_params": sanitized_req,
        "metrics_summary": sanitized_metrics,
        "result_cached": sanitized_result,
        "details": sanitized_details,
    }

    # Prepend to keep newest first and cap at maximum size
    history.insert(0, new_entry)
    st.session_state[_HISTORY_KEY] = history[:_MAX_HISTORY_ITEMS]


def update_session_analysis_status(
    activity_id: str,
    status: str,
    summary: str = "",
    metrics_summary: dict[str, Any] | None = None,
    result_cached: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Update status, summary, and metrics of an existing analysis in session history."""
    if not activity_id:
        return

    history = get_session_history()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for entry in history:
        if entry.get("activity_id") == activity_id:
            entry["status"] = status
            if summary:
                entry["summary"] = summary
            if metrics_summary:
                entry["metrics_summary"] = _sanitize_dict_for_storage(metrics_summary)
            if result_cached:
                entry["result_cached"] = _sanitize_dict_for_storage(result_cached)
            if details:
                entry["details"] = _sanitize_dict_for_storage(details)
            entry["updated_at"] = now_str
            st.session_state[_HISTORY_KEY] = history
            return


def filter_session_history(
    analysis_type: str = "All",
    status: str = "All",
    sort_order: str = "Newest",
) -> list[dict[str, Any]]:
    """
    Filter and sort session history entries.
    """
    history = get_session_history()
    filtered: list[dict[str, Any]] = []

    for entry in history:
        # Filter by analysis type
        if analysis_type != "All":
            etype = entry.get("analysis_type", "")
            if analysis_type.lower() not in etype.lower():
                continue

        # Filter by status
        if status != "All":
            estatus = entry.get("status", "")
            if status.lower() != estatus.lower():
                continue

        filtered.append(entry)

    # Sort
    if sort_order == "Oldest":
        filtered.reverse()

    return filtered


def find_related_analyses(
    target_entry: Any,
    all_entries: Sequence[Any],
) -> list[dict[str, Any]]:
    """
    Identify other session analyses that share date or location context.

    Note: Relationship is purely contextual for reference, not causal.
    """
    if hasattr(target_entry, "to_dict"):
        target_dict = target_entry.to_dict()
    elif isinstance(target_entry, Mapping):
        target_dict = dict(target_entry)
    else:
        target_dict = {"analysis_id": str(target_entry), "activity_id": str(target_entry)}

    target_id = target_dict.get("activity_id") or target_dict.get("analysis_id")
    target_date = str(target_dict.get("date", "") or (target_dict.get("request_params", {}) or {}).get("date", ""))
    target_loc = target_dict.get("location_label") or target_dict.get("label")

    related: list[dict[str, Any]] = []
    for other in all_entries:
        if hasattr(other, "to_dict"):
            other_dict = other.to_dict()
        elif isinstance(other, Mapping):
            other_dict = dict(other)
        else:
            continue

        other_id = other_dict.get("activity_id") or other_dict.get("analysis_id")
        if other_id == target_id:
            continue

        other_req = other_dict.get("request_params") or {}
        other_date = str(other_dict.get("date", "") or other_req.get("date", ""))
        other_loc = other_dict.get("location_label") or other_dict.get("label")

        # Match on same analysis date or same location label
        if (target_date and other_date and target_date == other_date) or (
            target_loc and other_loc and target_loc == other_loc
        ):
            related.append(other_dict)

    return related


def clear_session_history() -> None:
    """Clear the session analysis history."""
    st.session_state[_HISTORY_KEY] = []
