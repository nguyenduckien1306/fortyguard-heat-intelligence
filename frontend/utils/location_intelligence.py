"""Location-Centric Intelligence Engine (Phase 17).

Groups completed analyses by exact normalized location and provides
per-location operational summaries. Uses exact coordinate/label matching only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        if f != f or abs(f) == float("inf"):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _get_record_dict(r: Any) -> dict[str, Any]:
    if hasattr(r, "to_dict"):
        return dict(r.to_dict())
    if isinstance(r, Mapping):
        return dict(r)
    return {}


def _get_location_key(rd: dict) -> str | None:
    loc = rd.get("location_label") or rd.get("location") or rd.get("label")
    if loc and isinstance(loc, str) and loc.strip():
        return loc.strip()
    return None


def _get_date(rd: dict) -> str | None:
    d = rd.get("date") or (rd.get("created_at", "")[:10] if rd.get("created_at") else None)
    if d and isinstance(d, str) and len(d) >= 4:
        return d
    return None


@dataclass(frozen=True)
class LocationSummary:
    """Immutable per-location intelligence summary."""

    location: str
    total_analyses: int
    latest_observation: float | None
    previous_observation: float | None
    temperature_change: float | None
    latest_date: str | None
    earliest_date: str | None
    active_alerts: int
    open_investigations: int
    watchlists_matched: int
    analysis_ids: list[str]
    data_quality: str
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_location_summaries(
    records: Sequence[Any] | None = None,
    alerts: Sequence[Any] | None = None,
    queue_items: Sequence[Any] | None = None,
    watchlist_evaluations: Sequence[Any] | None = None,
) -> list[LocationSummary]:
    """Build per-location summaries from session data."""
    rec_list = [_get_record_dict(r) for r in (records or [])]
    alert_list = [_get_record_dict(a) for a in (alerts or [])]
    queue_list = [_get_record_dict(q) for q in (queue_items or [])]
    wl_eval_list = [_get_record_dict(w) for w in (watchlist_evaluations or [])]

    # Group records by location
    loc_groups: dict[str, list[dict]] = {}
    for rd in rec_list:
        loc = _get_location_key(rd)
        if loc:
            loc_groups.setdefault(loc, []).append(rd)

    # Group alerts by location
    loc_alerts: dict[str, int] = {}
    for ad in alert_list:
        loc = _get_location_key(ad)
        status = str(ad.get("status", "ACTIVE")).upper()
        if loc and status not in ("RESOLVED", "DISMISSED", "SUPPRESSED"):
            loc_alerts[loc] = loc_alerts.get(loc, 0) + 1

    # Group investigations by location (via analysis_id linkage)
    aid_to_loc: dict[str, str] = {}
    for rd in rec_list:
        aid = str(rd.get("analysis_id", ""))
        loc = _get_location_key(rd)
        if aid and loc:
            aid_to_loc[aid] = loc

    loc_investigations: dict[str, int] = {}
    for qd in queue_list:
        q_status = str(qd.get("status", "OPEN")).upper()
        if q_status in ("OPEN", "IN_REVIEW", "IN REVIEW"):
            q_aid = str(qd.get("analysis_id", ""))
            loc = _get_location_key(qd) or aid_to_loc.get(q_aid)
            if loc:
                loc_investigations[loc] = loc_investigations.get(loc, 0) + 1

    # Group watchlist evaluations by location
    loc_wl: dict[str, int] = {}
    for wd in wl_eval_list:
        if wd.get("matched") or wd.get("status") == "TRIGGERED":
            w_aid = str(wd.get("analysis_id", ""))
            loc = aid_to_loc.get(w_aid)
            if loc:
                loc_wl[loc] = loc_wl.get(loc, 0) + 1

    results: list[LocationSummary] = []

    for loc, recs in sorted(loc_groups.items()):
        # Sort by date
        dated = sorted(recs, key=lambda rd: _get_date(rd) or "")
        analysis_ids = [str(rd.get("analysis_id", "UNKNOWN")) for rd in dated]

        # Extract temperatures
        temps: list[tuple[str, float]] = []
        for rd in dated:
            metrics = rd.get("metrics", {}) if isinstance(rd.get("metrics"), dict) else {}
            t = _safe_float(rd.get("observed_temperature")) or _safe_float(metrics.get("mean_temp"))
            d = _get_date(rd) or ""
            if t is not None:
                temps.append((d, t))

        latest_obs = temps[-1][1] if temps else None
        prev_obs = temps[-2][1] if len(temps) >= 2 else None
        temp_change = round(latest_obs - prev_obs, 4) if latest_obs is not None and prev_obs is not None else None

        dates = [_get_date(rd) for rd in dated]
        clean_dates = sorted([d for d in dates if d])

        # Data quality (worst of all records at this location)
        dq_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "INSUFFICIENT": 0}
        qualities = []
        for rd in recs:
            dq = rd.get("data_quality")
            if dq and isinstance(dq, str):
                qualities.append(dq.upper())
            else:
                qualities.append("HIGH")
        worst_dq = min(qualities, key=lambda q: dq_rank.get(q, 3)) if qualities else "HIGH"

        limitations = ["Location grouping uses exact label matching only."]
        if len(recs) < 3:
            limitations.append("Limited observations. Pattern assessment requires more data.")

        results.append(LocationSummary(
            location=loc,
            total_analyses=len(recs),
            latest_observation=latest_obs,
            previous_observation=prev_obs,
            temperature_change=temp_change,
            latest_date=clean_dates[-1] if clean_dates else None,
            earliest_date=clean_dates[0] if clean_dates else None,
            active_alerts=loc_alerts.get(loc, 0),
            open_investigations=loc_investigations.get(loc, 0),
            watchlists_matched=loc_wl.get(loc, 0),
            analysis_ids=analysis_ids,
            data_quality=worst_dq,
            limitations=limitations,
        ))

    return results
