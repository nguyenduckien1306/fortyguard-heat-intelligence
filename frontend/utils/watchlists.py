"""Session-Local Watchlist Management and Configuration.

Provides pure session-local watchlists with multi-criteria conditions,
temporal comparison modes, anti-flapping hysteresis, and strict capacity limits.

Strict Invariants:
1. Session-local storage only in st.session_state (zero DB, zero external disk/cloud).
2. Maximum 20 active watchlists.
3. Watchlist names maximum 60 characters.
4. Deterministic validation (finite numbers, valid operators, supported metrics).
5. Watchlist duplication performs deep copies ensuring no shared mutable state.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
import math
from typing import Any, Mapping, Sequence
import streamlit as st

from frontend.utils.clock import Clock, get_current_clock

_WATCHLISTS_STORE_KEY = "_session_watchlists_store"
_WATCHLIST_COUNTER_KEY = "_session_watchlist_id_counter"

MAX_WATCHLISTS: int = 20
MAX_WATCHLIST_NAME_LENGTH: int = 60
MAX_CRITERIA_PER_WATCHLIST: int = 10

SUPPORTED_CRITERIA_METRICS: frozenset[str] = frozenset({
    "mean_temperature",
    "temperature_change",
    "temperature_change_percent",
    "temperature_spread",
    "above_threshold_proportion",
    "analysis_count",
})

SUPPORTED_OPERATORS: frozenset[str] = frozenset({">", ">=", "<", "<=", "==", "!="})
SUPPORTED_COMPARISON_MODES: frozenset[str] = frozenset({"PREVIOUS", "FIRST", "ROLLING"})


@dataclass(frozen=True)
class WatchlistCriterion:
    """Immutable single threshold condition within a Watchlist."""

    metric: str
    operator: str
    threshold: float
    tolerance: float = 1e-6
    trigger_threshold: float | None = None
    clear_threshold: float | None = None
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WatchlistCriterion:
        try:
            th = float(data.get("threshold", 0.0))
        except (ValueError, TypeError):
            th = 0.0

        trig = None
        if data.get("trigger_threshold") is not None:
            try:
                trig = float(data["trigger_threshold"])
            except (ValueError, TypeError):
                trig = None

        clr = None
        if data.get("clear_threshold") is not None:
            try:
                clr = float(data["clear_threshold"])
            except (ValueError, TypeError):
                clr = None

        return cls(
            metric=str(data.get("metric", "mean_temperature")).strip().lower(),
            operator=str(data.get("operator", ">")).strip(),
            threshold=th,
            tolerance=float(data.get("tolerance", 1e-6)),
            trigger_threshold=trig,
            clear_threshold=clr,
            version=int(data.get("version", 1)),
        )


@dataclass
class Watchlist:
    """Configurable Watchlist model for monitoring completed session analyses."""

    watchlist_id: str
    name: str
    description: str = ""
    criteria: list[WatchlistCriterion] = field(default_factory=list)
    location_scope: str = "all"
    analysis_type_scope: str = "all"
    comparison_mode: str = "PREVIOUS"  # "PREVIOUS" | "FIRST" | "ROLLING"
    window_size: int = 5
    enabled: bool = True
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["criteria"] = [c.to_dict() if isinstance(c, WatchlistCriterion) else dict(c) for c in self.criteria]
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Watchlist:
        raw_crit = data.get("criteria", [])
        crit_list: list[WatchlistCriterion] = []
        if isinstance(raw_crit, Sequence):
            for c in raw_crit:
                if isinstance(c, WatchlistCriterion):
                    crit_list.append(c)
                elif isinstance(c, Mapping):
                    crit_list.append(WatchlistCriterion.from_dict(c))

        return cls(
            watchlist_id=str(data.get("watchlist_id", "")),
            name=str(data.get("name", "Untitled Watchlist")).strip(),
            description=str(data.get("description", "")).strip(),
            criteria=crit_list,
            location_scope=str(data.get("location_scope", "all")).strip(),
            analysis_type_scope=str(data.get("analysis_type_scope", "all")).strip(),
            comparison_mode=str(data.get("comparison_mode", "PREVIOUS")).strip().upper(),
            window_size=int(data.get("window_size", 5)),
            enabled=bool(data.get("enabled", True)),
            version=int(data.get("version", 1)),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )


def validate_watchlist_criterion(criterion: WatchlistCriterion | Mapping[str, Any]) -> tuple[bool, str | None]:
    """Validate a single WatchlistCriterion."""
    c_dict = criterion.to_dict() if isinstance(criterion, WatchlistCriterion) else dict(criterion)

    metric = str(c_dict.get("metric", "")).strip().lower()
    if metric not in SUPPORTED_CRITERIA_METRICS:
        return False, f"Invalid criterion metric '{metric}'. Supported metrics: {', '.join(sorted(SUPPORTED_CRITERIA_METRICS))}."

    op = str(c_dict.get("operator", "")).strip()
    if op not in SUPPORTED_OPERATORS:
        return False, f"Invalid operator '{op}'. Supported operators: {', '.join(sorted(SUPPORTED_OPERATORS))}."

    th = c_dict.get("threshold")
    if th is None:
        return False, "Threshold value cannot be None."
    try:
        th_f = float(th)
        if math.isnan(th_f) or math.isinf(th_f):
            return False, "Threshold must be a valid finite number."
    except (ValueError, TypeError):
        return False, f"Invalid threshold value '{th}'."

    # Validate Hysteresis if specified
    trig = c_dict.get("trigger_threshold")
    clr = c_dict.get("clear_threshold")
    if trig is not None and clr is not None:
        try:
            trig_f = float(trig)
            clr_f = float(clr)
            if op in (">", ">=") and trig_f <= clr_f:
                return False, f"Trigger threshold ({trig_f}) must be strictly greater than clear threshold ({clr_f}) for positive operator '{op}'."
            elif op in ("<", "<=") and trig_f >= clr_f:
                return False, f"Trigger threshold ({trig_f}) must be strictly less than clear threshold ({clr_f}) for negative operator '{op}'."
        except (ValueError, TypeError):
            return False, "Hysteresis thresholds must be valid finite numbers."

    return True, None


def validate_watchlist(watchlist: Watchlist | Mapping[str, Any]) -> tuple[bool, str | None]:
    """Validate a Watchlist against all operational invariants."""
    w_dict = watchlist.to_dict() if isinstance(watchlist, Watchlist) else dict(watchlist)

    name = str(w_dict.get("name", "")).strip()
    if not name:
        return False, "Watchlist name cannot be empty."
    if len(name) > MAX_WATCHLIST_NAME_LENGTH:
        return False, f"Watchlist name exceeds maximum allowed length of {MAX_WATCHLIST_NAME_LENGTH} characters."

    comp_mode = str(w_dict.get("comparison_mode", "PREVIOUS")).strip().upper()
    if comp_mode not in SUPPORTED_COMPARISON_MODES:
        return False, f"Invalid comparison mode '{comp_mode}'. Supported modes: {', '.join(sorted(SUPPORTED_COMPARISON_MODES))}."

    win_size = w_dict.get("window_size", 5)
    try:
        win_size_i = int(win_size)
        if win_size_i < 1 or win_size_i > 50:
            return False, "Window size must be an integer between 1 and 50."
    except (ValueError, TypeError):
        return False, "Window size must be a valid integer."

    criteria = w_dict.get("criteria", [])
    if not criteria:
        return False, "Watchlist must contain at least one criterion."
    if len(criteria) > MAX_CRITERIA_PER_WATCHLIST:
        return False, f"Watchlist exceeds maximum allowed criteria limit of {MAX_CRITERIA_PER_WATCHLIST}."

    seen_criteria_keys: set[str] = set()
    for c in criteria:
        ok, err = validate_watchlist_criterion(c)
        if not ok:
            return False, err
        c_obj = WatchlistCriterion.from_dict(c) if isinstance(c, Mapping) else c
        c_key = f"{c_obj.metric}:{c_obj.operator}:{c_obj.threshold}"
        if c_key in seen_criteria_keys:
            return False, f"Duplicate identical criterion detected: {c_key}."
        seen_criteria_keys.add(c_key)

    return True, None


# ──────────────────────────────────────────────────────────────────────────────
# Storage & Session Operations
# ──────────────────────────────────────────────────────────────────────────────


def _get_raw_watchlists() -> list[dict[str, Any]]:
    if _WATCHLISTS_STORE_KEY not in st.session_state:
        st.session_state[_WATCHLISTS_STORE_KEY] = []
    return st.session_state[_WATCHLISTS_STORE_KEY]


def generate_watchlist_id() -> str:
    """Generate a collision-free session-local Watchlist ID."""
    if _WATCHLIST_COUNTER_KEY not in st.session_state:
        st.session_state[_WATCHLIST_COUNTER_KEY] = 0
    st.session_state[_WATCHLIST_COUNTER_KEY] += 1
    return f"WL-{st.session_state[_WATCHLIST_COUNTER_KEY]:03d}"


def get_watchlists() -> list[Watchlist]:
    """Retrieve all configured Watchlists from session state."""
    raw = _get_raw_watchlists()
    if not raw and "_wl_initialized" not in st.session_state:
        st.session_state["_wl_initialized"] = True
        return reset_default_watchlists()
    return [Watchlist.from_dict(d) for d in raw if isinstance(d, Mapping)]


def get_watchlist(watchlist_id: str) -> Watchlist | None:
    """Retrieve a single Watchlist by its ID."""
    if not watchlist_id:
        return None
    for wl in get_watchlists():
        if wl.watchlist_id == watchlist_id:
            return wl
    return None


def save_watchlist(watchlist: Watchlist, clock: Clock | None = None) -> tuple[bool, str | None, Watchlist | None]:
    """Create or update a Watchlist in session state."""
    ok, err = validate_watchlist(watchlist)
    if not ok:
        return False, err, None

    clk = clock or get_current_clock()
    now_str = clk.now_iso()

    raw_list = _get_raw_watchlists()

    # Check if updating existing
    for idx, existing in enumerate(raw_list):
        if existing.get("watchlist_id") == watchlist.watchlist_id:
            # Updating existing: increment version and update timestamp
            watchlist.version = int(existing.get("version", 1)) + 1
            if not watchlist.created_at:
                watchlist.created_at = str(existing.get("created_at", now_str))
            watchlist.updated_at = now_str

            raw_list[idx] = watchlist.to_dict()
            st.session_state[_WATCHLISTS_STORE_KEY] = raw_list
            return True, None, watchlist

    # Creating new watchlist — check capacity limit (20)
    if len(raw_list) >= MAX_WATCHLISTS:
        return False, f"Maximum watchlist capacity ({MAX_WATCHLISTS}) reached. Delete an existing watchlist to create a new one.", None

    if not watchlist.watchlist_id:
        watchlist.watchlist_id = generate_watchlist_id()
    if not watchlist.created_at:
        watchlist.created_at = now_str
    watchlist.updated_at = now_str
    watchlist.version = 1

    raw_list.append(watchlist.to_dict())
    st.session_state[_WATCHLISTS_STORE_KEY] = raw_list
    return True, None, watchlist


def delete_watchlist(watchlist_id: str) -> bool:
    """Delete a Watchlist by ID from session state."""
    if not watchlist_id:
        return False
    raw_list = _get_raw_watchlists()
    initial_len = len(raw_list)
    filtered = [d for d in raw_list if d.get("watchlist_id") != watchlist_id]
    if len(filtered) < initial_len:
        st.session_state[_WATCHLISTS_STORE_KEY] = filtered
        return True
    return False


def toggle_watchlist(watchlist_id: str, clock: Clock | None = None) -> bool:
    """Toggle the enabled state of a Watchlist."""
    wl = get_watchlist(watchlist_id)
    if not wl:
        return False
    wl.enabled = not wl.enabled
    ok, _, _ = save_watchlist(wl, clock=clock)
    return ok


def duplicate_watchlist(
    watchlist_id: str,
    new_name: str | None = None,
    clock: Clock | None = None,
) -> tuple[bool, str | None, Watchlist | None]:
    """Deep-copy an existing Watchlist with a new ID, preserving source immutability."""
    source = get_watchlist(watchlist_id)
    if not source:
        return False, f"Source watchlist '{watchlist_id}' not found.", None

    # Deep-copy criteria and attributes
    copied_criteria = [WatchlistCriterion.from_dict(c.to_dict()) for c in source.criteria]
    target_name = (new_name or f"Copy of {source.name}")[:MAX_WATCHLIST_NAME_LENGTH]

    new_wl = Watchlist(
        watchlist_id=generate_watchlist_id(),
        name=target_name,
        description=source.description,
        criteria=copied_criteria,
        location_scope=source.location_scope,
        analysis_type_scope=source.analysis_type_scope,
        comparison_mode=source.comparison_mode,
        window_size=source.window_size,
        enabled=source.enabled,
        version=1,
    )

    return save_watchlist(new_wl, clock=clock)


def get_default_watchlists() -> list[Watchlist]:
    """Return default seed watchlists for fresh session states."""
    return [
        Watchlist(
            watchlist_id="WL-001",
            name="Extreme Temperature Watch",
            description="Monitors analyses where observed mean temperature exceeds 38°C.",
            criteria=[
                WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=38.0, trigger_threshold=38.0, clear_threshold=36.0),
            ],
            location_scope="all",
            comparison_mode="PREVIOUS",
            enabled=True,
            version=1,
        ),
        Watchlist(
            watchlist_id="WL-002",
            name="Rapid Warming Trend",
            description="Detects location thermal increases exceeding +2.0°C between consecutive analyses.",
            criteria=[
                WatchlistCriterion(metric="temperature_change", operator=">=", threshold=2.0),
            ],
            location_scope="all",
            comparison_mode="PREVIOUS",
            enabled=True,
            version=1,
        ),
        Watchlist(
            watchlist_id="WL-003",
            name="High Spatial Heterogeneity",
            description="Flags analyses with temperature spread across tiles exceeding 10°C.",
            criteria=[
                WatchlistCriterion(metric="temperature_spread", operator=">=", threshold=10.0),
            ],
            location_scope="all",
            comparison_mode="PREVIOUS",
            enabled=True,
            version=1,
        ),
    ]


def reset_default_watchlists(clock: Clock | None = None) -> list[Watchlist]:
    """Reset session watchlists to default presets."""
    defaults = get_default_watchlists()
    clk = clock or get_current_clock()
    now_str = clk.now_iso()

    st.session_state[_WATCHLISTS_STORE_KEY] = []
    st.session_state[_WATCHLIST_COUNTER_KEY] = len(defaults)

    saved_list: list[Watchlist] = []
    for wl in defaults:
        wl.created_at = now_str
        wl.updated_at = now_str
        saved_list.append(wl)

    st.session_state[_WATCHLISTS_STORE_KEY] = [w.to_dict() for w in saved_list]
    return saved_list
