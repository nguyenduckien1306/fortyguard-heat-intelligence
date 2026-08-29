"""Canonical AnalysisRecord and session-local Analysis Workspace history manager.

Strict Session-Local Boundary:
- History lives exclusively in st.session_state.
- Zero databases, zero disk persistence, zero external telemetry.
- Zero new FortyGuard API calls: inspecting, reopening, searching, filtering,
  pinning, tagging, deleting, or clearing makes ZERO network requests.
- Deeply sanitized: never stores API keys, tokens, signed URLs, or credentials.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date as dt_date, datetime, timedelta
import re
from typing import Any, Mapping
import streamlit as st

from frontend.utils.tags import (
    add_analysis_tag as _sync_add_tag,
    get_analysis_tags as _sync_get_tags,
    is_analysis_pinned as _sync_is_pinned,
    normalize_analysis_tag,
    pin_analysis as _sync_pin,
    remove_analysis_tag as _sync_remove_tag,
    unpin_analysis as _sync_unpin,
)

_RECORDS_STORE_KEY = "_session_analysis_records"
_COUNTERS_STORE_KEY = "_session_analysis_counters"

MAX_HISTORY_RECORDS = 50
MAX_PINNED_RECORDS = 10
MAX_TAGS_PER_RECORD = 10
MAX_TAG_LENGTH = 30

_SECRET_KEYS_REGEX = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|signed[_-]?url|download[_-]?link|credentials|bearer)"
)


# ──────────────────────────────────────────────────────────────────────────────
# Deep Recursive Sanitizer
# ──────────────────────────────────────────────────────────────────────────────


def sanitize_value_for_history(val: Any) -> Any:
    """Recursively strip sensitive credentials, API keys, and signed URLs."""
    if isinstance(val, Mapping):
        cleaned: dict[str, Any] = {}
        for k, v in val.items():
            if _SECRET_KEYS_REGEX.search(str(k)):
                continue
            if isinstance(v, str) and ("X-Amz-Signature=" in v or _SECRET_KEYS_REGEX.search(v)):
                continue
            cleaned[k] = sanitize_value_for_history(v)
        return cleaned
    elif isinstance(val, (list, tuple)):
        return [sanitize_value_for_history(item) for item in val]
    elif isinstance(val, str):
        if "X-Amz-Signature=" in val:
            return "[REDACTED_SIGNED_URL]"
        return val
    return val


# ──────────────────────────────────────────────────────────────────────────────
# Canonical AnalysisRecord Dataclass
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class AnalysisRecord:
    """Canonical, controlled session-local record for a completed or recorded analysis."""

    analysis_id: str
    activity_id: str
    analysis_type: str  # "heat_intelligence" | "heatmap"
    created_at: str
    updated_at: str
    location_label: str
    latitude: float | None = None
    longitude: float | None = None
    date: str = ""
    time: str | None = None
    observed_temperature: float | None = None
    categories: list[str] = field(default_factory=list)
    granularity: int | None = None
    polygon_summary: str = ""
    polygon_aoi: dict[str, Any] | None = None
    status: str = "Completed"
    summary: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    insights: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    pinned: bool = False
    result_cached: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert record to a sanitized dictionary."""
        return sanitize_value_for_history(asdict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AnalysisRecord:
        """Construct record from a sanitized dictionary."""
        clean = sanitize_value_for_history(data)
        return cls(
            analysis_id=str(clean.get("analysis_id", "")),
            activity_id=str(clean.get("activity_id", "")),
            analysis_type=str(clean.get("analysis_type", "heatmap")),
            created_at=str(clean.get("created_at", "")),
            updated_at=str(clean.get("updated_at", "")),
            location_label=str(clean.get("location_label", "Analysis")),
            latitude=clean.get("latitude"),
            longitude=clean.get("longitude"),
            date=str(clean.get("date", "")),
            time=clean.get("time"),
            observed_temperature=clean.get("observed_temperature"),
            categories=list(clean.get("categories", [])),
            granularity=clean.get("granularity"),
            polygon_summary=str(clean.get("polygon_summary", "")),
            polygon_aoi=clean.get("polygon_aoi"),
            status=str(clean.get("status", "Completed")),
            summary=str(clean.get("summary", "")),
            metrics=dict(clean.get("metrics", {})),
            insights=list(clean.get("insights", [])),
            tags=list(clean.get("tags", [])),
            pinned=bool(clean.get("pinned", False)),
            result_cached=clean.get("result_cached"),
        )


# ──────────────────────────────────────────────────────────────────────────────
# ID Generator
# ──────────────────────────────────────────────────────────────────────────────


def generate_analysis_id(analysis_type: str) -> str:
    """Generate a collision-safe, deterministic, human-readable session ID."""
    prefix = "HI" if "heat_intelligence" in analysis_type.lower() else "HM"
    today_str = datetime.now().strftime("%Y%m%d")

    if _COUNTERS_STORE_KEY not in st.session_state:
        st.session_state[_COUNTERS_STORE_KEY] = {}

    counters = st.session_state[_COUNTERS_STORE_KEY]
    counter_key = f"{prefix}-{today_str}"
    current_count = counters.get(counter_key, 0) + 1
    counters[counter_key] = current_count
    st.session_state[_COUNTERS_STORE_KEY] = counters

    return f"{prefix}-{today_str}-{current_count:03d}"


# ──────────────────────────────────────────────────────────────────────────────
# Storage & History Operations
# ──────────────────────────────────────────────────────────────────────────────


def _get_records_store() -> list[dict[str, Any]]:
    """Retrieve raw session records store."""
    if _RECORDS_STORE_KEY not in st.session_state:
        st.session_state[_RECORDS_STORE_KEY] = []
    return st.session_state[_RECORDS_STORE_KEY]


def list_analysis_records() -> list[AnalysisRecord]:
    """List all stored analysis records in session state, including legacy bridge."""
    raw_list = _get_records_store()
    records: list[AnalysisRecord] = []
    seen_acts: set[str] = set()

    for raw in raw_list:
        rec = AnalysisRecord.from_dict(raw)
        # Keep pin state synced with tags module
        if rec.activity_id and _sync_is_pinned(rec.activity_id):
            rec.pinned = True
        # Keep tags synced with tags module
        if rec.activity_id:
            synced_tags = _sync_get_tags(rec.activity_id)
            if synced_tags:
                rec.tags = synced_tags
            seen_acts.add(rec.activity_id)
        records.append(rec)

    # Bridge entries from legacy history store if not already present (only Completed records)
    from frontend.utils.history import get_session_history
    for entry in get_session_history():
        act_id = entry.get("activity_id", "")
        status_val = str(entry.get("status", "")).strip().capitalize()
        if act_id and act_id not in seen_acts and status_val == "Completed":
            raw_req = entry.get("request_params") or {}
            rec = AnalysisRecord(
                analysis_id=generate_analysis_id(entry.get("analysis_type", "heatmap")),
                activity_id=act_id,
                analysis_type=entry.get("analysis_type", "heatmap"),
                created_at=entry.get("created_at", ""),
                updated_at=entry.get("updated_at", ""),
                location_label=entry.get("label", "Analysis"),
                latitude=raw_req.get("latitude"),
                longitude=raw_req.get("longitude"),
                date=str(raw_req.get("date", "")),
                time=raw_req.get("time"),
                observed_temperature=raw_req.get("temperature"),
                categories=list(raw_req.get("analysis", [])),
                granularity=raw_req.get("granularity"),
                polygon_aoi=raw_req.get("polygon_aoi"),
                status="Completed",
                summary=entry.get("summary", ""),
                metrics=dict(entry.get("metrics_summary") or {}),
                result_cached=entry.get("result_cached"),
            )
            records.append(rec)
            seen_acts.add(act_id)

    return records


def get_analysis_record(analysis_id: str) -> AnalysisRecord | None:
    """Retrieve a single analysis record by its session-local analysis ID."""
    if not analysis_id:
        return None
    for rec in list_analysis_records():
        if rec.analysis_id == analysis_id:
            return rec
    return None


def get_analysis_record_by_activity_id(activity_id: str) -> AnalysisRecord | None:
    """Retrieve an analysis record by its backend activity ID."""
    if not activity_id:
        return None
    for rec in list_analysis_records():
        if rec.activity_id == activity_id:
            return rec
    return None


def add_analysis_record(record: AnalysisRecord) -> AnalysisRecord:
    """Add or update an AnalysisRecord in session history with trimming policy.

    Trimming Policy:
    - Max capacity: 50 records.
    - When adding the 51st item, remove the oldest unpinned record.
    - Never automatically remove a pinned record.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw_list = _get_records_store()

    # Check if a record with this activity_id or analysis_id already exists (idempotent update)
    for i, existing in enumerate(raw_list):
        if (
            (record.activity_id and existing.get("activity_id") == record.activity_id)
            or (record.analysis_id and existing.get("analysis_id") == record.analysis_id)
        ):
            if not record.analysis_id:
                record.analysis_id = str(existing.get("analysis_id", ""))
            if not record.created_at:
                record.created_at = str(existing.get("created_at", now_str))
            record.updated_at = now_str
            clean_dict = record.to_dict()
            raw_list[i] = clean_dict
            st.session_state[_RECORDS_STORE_KEY] = raw_list
            return record

    if not record.created_at:
        record.created_at = now_str
    record.updated_at = now_str

    if not record.analysis_id:
        record.analysis_id = generate_analysis_id(record.analysis_type)

    # Sanitize before saving
    clean_dict = record.to_dict()

    # Check capacity limit (50)
    if len(raw_list) >= MAX_HISTORY_RECORDS:
        # Find the oldest unpinned record from the tail (oldest items are at the end)
        unpinned_idx = None
        for idx in range(len(raw_list) - 1, -1, -1):
            act_id = raw_list[idx].get("activity_id", "")
            is_pinned = raw_list[idx].get("pinned", False) or (act_id and _sync_is_pinned(act_id))
            if not is_pinned:
                unpinned_idx = idx
                break

        if unpinned_idx is not None:
            raw_list.pop(unpinned_idx)
        # If all items are pinned (defensive, at most 10), do not delete anything

    # Prepend new record (newest first)
    raw_list.insert(0, clean_dict)
    st.session_state[_RECORDS_STORE_KEY] = raw_list

    # Also sync tags & pins if present
    if record.activity_id:
        if record.tags:
            from frontend.utils.tags import set_analysis_tags
            set_analysis_tags(record.activity_id, record.tags)
        if record.pinned:
            _sync_pin(record.activity_id)

    # Sync with legacy history module so existing callers remain 100% compatible
    from frontend.utils.history import record_session_analysis
    record_session_analysis(
        analysis_type=record.analysis_type,
        activity_id=record.activity_id,
        label=record.location_label,
        status=record.status,
        summary=record.summary,
        request_params={
            "latitude": record.latitude,
            "longitude": record.longitude,
            "date": record.date,
            "time": record.time,
            "analysis": record.categories,
            "granularity": record.granularity,
            "polygon_aoi": record.polygon_aoi,
        },
        metrics_summary=record.metrics,
        result_cached=record.result_cached,
    )

    return record


def delete_analysis_record(analysis_id: str) -> bool:
    """Delete a single analysis record by analysis_id."""
    if not analysis_id:
        return False

    raw_list = _get_records_store()
    target_idx = None
    act_id = None

    for idx, rec in enumerate(raw_list):
        if rec.get("analysis_id") == analysis_id:
            target_idx = idx
            act_id = rec.get("activity_id")
            break

    if target_idx is None:
        return False

    raw_list.pop(target_idx)
    st.session_state[_RECORDS_STORE_KEY] = raw_list

    if act_id:
        _sync_unpin(act_id)
        from frontend.utils.tags import set_analysis_tags
        set_analysis_tags(act_id, [])

    # If active detail view was viewing this deleted analysis, reset it
    if st.session_state.get("_active_detail_analysis_id") == analysis_id:
        st.session_state["_active_detail_analysis_id"] = None

    return True


def clear_all_analysis_records() -> None:
    """Clear all analysis records from session history."""
    st.session_state[_RECORDS_STORE_KEY] = []
    st.session_state["_active_detail_analysis_id"] = None
    from frontend.utils.tags import clear_pins, clear_tags
    clear_pins()
    clear_tags()
    from frontend.utils.history import clear_session_history
    clear_session_history()


# ──────────────────────────────────────────────────────────────────────────────
# Pin & Tag Record Controls
# ──────────────────────────────────────────────────────────────────────────────


def pin_analysis_record(analysis_id: str) -> tuple[bool, str | None]:
    """Pin an analysis record. Maximum 10 pinned records."""
    rec = get_analysis_record(analysis_id)
    if not rec:
        return False, "Analysis not found."

    # Check pinned count
    all_records = list_analysis_records()
    pinned_count = sum(1 for r in all_records if r.pinned)

    if rec.pinned:
        return True, None

    if pinned_count >= MAX_PINNED_RECORDS:
        return False, "Maximum of 10 pinned analyses reached. Unpin another analysis first."

    rec.pinned = True
    add_analysis_record(rec)
    if rec.activity_id:
        _sync_pin(rec.activity_id)

    return True, None


def unpin_analysis_record(analysis_id: str) -> bool:
    """Unpin an analysis record."""
    rec = get_analysis_record(analysis_id)
    if not rec or not rec.pinned:
        return False

    rec.pinned = False
    add_analysis_record(rec)
    if rec.activity_id:
        _sync_unpin(rec.activity_id)

    return True


def add_tag_to_analysis_record(analysis_id: str, tag: str) -> tuple[bool, str | None]:
    """Add a tag to an analysis record following normalization and limits."""
    rec = get_analysis_record(analysis_id)
    if not rec:
        return False, "Analysis not found."

    norm = normalize_analysis_tag(tag)
    if not norm:
        return False, "Invalid tag. Tags must be 1-30 characters."

    if norm in rec.tags:
        return True, None

    if len(rec.tags) >= MAX_TAGS_PER_RECORD:
        return False, "Maximum of 10 tags reached for this analysis."

    rec.tags.append(norm)
    add_analysis_record(rec)
    if rec.activity_id:
        _sync_add_tag(rec.activity_id, norm)

    return True, None


def remove_tag_from_analysis_record(analysis_id: str, tag: str) -> bool:
    """Remove a tag from an analysis record."""
    rec = get_analysis_record(analysis_id)
    if not rec:
        return False

    norm = normalize_analysis_tag(tag) or tag.strip().lower()
    if norm not in rec.tags:
        return False

    rec.tags = [t for t in rec.tags if t != norm]
    add_analysis_record(rec)
    if rec.activity_id:
        _sync_remove_tag(rec.activity_id, norm)

    return True


# ──────────────────────────────────────────────────────────────────────────────
# Search, Filter & Deterministic Sort
# ──────────────────────────────────────────────────────────────────────────────


def search_and_filter_records(
    query: str = "",
    type_filter: str = "All",
    status_filter: str = "All",
    pinned_only: bool = False,
    tag_filter: str | None = None,
    date_filter: str = "All",
    sort_by: str = "Newest",
) -> list[AnalysisRecord]:
    """Search, filter, and sort session records with deterministic ordering."""
    records = list_analysis_records()
    filtered: list[AnalysisRecord] = []

    clean_query = query.strip().lower()

    for rec in records:
        # Pinned filter
        if pinned_only and not rec.pinned:
            continue

        # Type filter
        if type_filter != "All":
            norm_type = type_filter.lower().replace(" ", "_")
            if norm_type not in rec.analysis_type.lower():
                continue

        # Status filter
        if status_filter != "All":
            if status_filter.lower() != rec.status.lower():
                continue

        # Tag filter
        if tag_filter and tag_filter != "All":
            norm_tag = tag_filter.strip().lower()
            if norm_tag not in [t.lower() for t in rec.tags]:
                continue

        # Date filter
        if date_filter != "All" and rec.date:
            try:
                rec_dt = datetime.strptime(rec.date, "%Y-%m-%d").date()
                today = dt_date.today()
                if date_filter == "Today" and rec_dt != today:
                    continue
                elif date_filter == "Last 7 Days" and rec_dt < (today - timedelta(days=7)):
                    continue
            except ValueError:
                pass

        # Text Query Search
        if clean_query:
            searchable_strings = [
                rec.analysis_id.lower(),
                rec.activity_id.lower(),
                rec.location_label.lower(),
                rec.analysis_type.lower(),
                rec.date.lower(),
                rec.summary.lower(),
                " ".join(t.lower() for t in rec.tags),
                " ".join(c.lower() for c in rec.categories),
            ]
            combined_haystack = " ".join(searchable_strings)
            if clean_query not in combined_haystack:
                continue

        filtered.append(rec)

    # Deterministic Sorting with tie-breakers
    if sort_by == "Oldest":
        filtered.sort(key=lambda r: (r.created_at, r.analysis_id))
    elif sort_by == "Pinned First":
        filtered.sort(key=lambda r: (not r.pinned, r.created_at, r.analysis_id), reverse=False)
        # Note: not r.pinned puts True (pinned) first when sorting asc
    elif sort_by == "Location A–Z":
        filtered.sort(key=lambda r: (r.location_label.lower(), r.created_at, r.analysis_id))
    else:  # "Newest" (default)
        filtered.sort(key=lambda r: (r.created_at, r.analysis_id), reverse=True)

    return filtered
