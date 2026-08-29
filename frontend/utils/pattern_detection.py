"""Cross-Analysis Pattern Detection Engine (Phase 17).

Identifies recurring descriptive patterns across completed session analyses.
All patterns are strictly observational — no causality, predictions, or medical claims.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from frontend.utils.clock import Clock, get_current_clock
from frontend.utils.responsible_analytics import RESPONSIBLE_ANALYTICS_NOTICE


@dataclass(frozen=True)
class Pattern:
    """Immutable descriptive pattern detected across analyses."""

    pattern_id: str
    pattern_type: str
    severity: str
    analysis_ids: list[str]
    dates: list[str]
    location: str | None
    evidence: list[str]
    count: int
    data_quality: str
    limitations: list[str]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Pattern type constants
PATTERN_REPEATED_THRESHOLD_EXCEEDANCE = "repeated_threshold_exceedance"
PATTERN_REPEATED_HIGH_TEMPERATURE = "repeated_high_temperature"
PATTERN_RECURRING_WATCHLIST_MATCH = "recurring_watchlist_match"
PATTERN_REPEATED_LOCATION_ALERTS = "repeated_location_alerts"
PATTERN_REPEATED_SIGNAL_TYPE = "repeated_signal_type"
PATTERN_DATA_QUALITY_DEGRADATION = "data_quality_degradation"
PATTERN_TEMPERATURE_DIRECTION = "temperature_direction"


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN
            return None
        if abs(f) == float("inf"):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _make_pattern_id(pattern_type: str, analysis_ids: list[str]) -> str:
    raw = f"{pattern_type}:{'|'.join(sorted(analysis_ids))}"
    return f"PAT-{hashlib.sha256(raw.encode()).hexdigest()[:12].upper()}"


def _get_record_dict(r: Any) -> dict[str, Any]:
    if hasattr(r, "to_dict"):
        return dict(r.to_dict())
    if isinstance(r, Mapping):
        return dict(r)
    return {}


def _get_location(r_dict: dict) -> str | None:
    loc = r_dict.get("location_label") or r_dict.get("location") or r_dict.get("label")
    if loc and isinstance(loc, str) and loc.strip():
        return loc.strip()
    return None


def _get_date(r_dict: dict) -> str | None:
    d = r_dict.get("date") or (r_dict.get("created_at", "")[:10] if r_dict.get("created_at") else None)
    if d and isinstance(d, str) and len(d) >= 4:
        return d
    return None


def _get_data_quality(r_dict: dict) -> str:
    dq = r_dict.get("data_quality")
    if dq and isinstance(dq, str):
        return dq.upper()
    return "HIGH"


def _worst_quality(qualities: list[str]) -> str:
    rank = {"INSUFFICIENT": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
    if not qualities:
        return "HIGH"
    return min(qualities, key=lambda q: rank.get(q.upper(), 3))


def detect_repeated_threshold_exceedance(records: Sequence[Any], threshold: float = 35.0) -> list[Pattern]:
    """Detect when multiple analyses exceed the same temperature threshold."""
    exceeding: list[dict] = []
    for r in records:
        rd = _get_record_dict(r)
        aid = rd.get("analysis_id", "UNKNOWN")
        metrics = rd.get("metrics", {})
        temp = _safe_float(rd.get("observed_temperature")) or _safe_float(metrics.get("mean_temp")) or _safe_float(
            metrics.get("observed_temperature"))
        if temp is not None and temp > threshold:
            exceeding.append(rd)

    if len(exceeding) < 2:
        return []

    aids = [str(rd.get("analysis_id", "UNKNOWN")) for rd in exceeding]
    dates = [_get_date(rd) for rd in exceeding]
    dates_clean = [d for d in dates if d]
    locations = [_get_location(rd) for rd in exceeding]
    loc = locations[0] if locations and all(l == locations[0] for l in locations) else None
    qualities = [_get_data_quality(rd) for rd in exceeding]

    return [Pattern(
        pattern_id=_make_pattern_id(PATTERN_REPEATED_THRESHOLD_EXCEEDANCE, aids),
        pattern_type=PATTERN_REPEATED_THRESHOLD_EXCEEDANCE,
        severity="ELEVATED" if len(exceeding) >= 3 else "WATCH",
        analysis_ids=aids,
        dates=dates_clean,
        location=loc,
        evidence=[f"Threshold {threshold}°C exceeded in {len(exceeding)} analyses."],
        count=len(exceeding),
        data_quality=_worst_quality(qualities),
        limitations=["Pattern is observational. Does not establish causation or predict future conditions."],
        explanation=f"{len(exceeding)} completed analyses exceeded the configured threshold of {threshold}°C.",
    )]


def detect_repeated_high_temperature(records: Sequence[Any], high_temp_threshold: float = 33.0) -> list[Pattern]:
    """Detect repeated high temperature observations."""
    high: list[dict] = []
    for r in records:
        rd = _get_record_dict(r)
        metrics = rd.get("metrics", {})
        temp = _safe_float(rd.get("observed_temperature")) or _safe_float(metrics.get("mean_temp"))
        if temp is not None and temp >= high_temp_threshold:
            high.append(rd)

    if len(high) < 2:
        return []

    aids = [str(rd.get("analysis_id", "UNKNOWN")) for rd in high]
    dates = [d for d in [_get_date(rd) for rd in high] if d]
    locations = [_get_location(rd) for rd in high]
    loc = locations[0] if locations and all(l == locations[0] for l in locations) else None
    qualities = [_get_data_quality(rd) for rd in high]

    return [Pattern(
        pattern_id=_make_pattern_id(PATTERN_REPEATED_HIGH_TEMPERATURE, aids),
        pattern_type=PATTERN_REPEATED_HIGH_TEMPERATURE,
        severity="ELEVATED" if len(high) >= 3 else "WATCH",
        analysis_ids=aids,
        dates=dates,
        location=loc,
        evidence=[f"Temperature ≥ {high_temp_threshold}°C observed in {len(high)} analyses."],
        count=len(high),
        data_quality=_worst_quality(qualities),
        limitations=["Observational pattern only. No causal inference."],
        explanation=f"{len(high)} analyses recorded temperatures at or above {high_temp_threshold}°C.",
    )]


def detect_recurring_watchlist_matches(
    watchlist_evaluations: Sequence[Any],
) -> list[Pattern]:
    """Detect watchlists matched by multiple analyses."""
    wl_groups: dict[str, list[dict]] = {}
    for we in watchlist_evaluations:
        wd = _get_record_dict(we)
        if not (wd.get("matched") or wd.get("status") == "TRIGGERED"):
            continue
        wl_id = str(wd.get("watchlist_id", "UNKNOWN"))
        wl_groups.setdefault(wl_id, []).append(wd)

    patterns = []
    for wl_id, matches in wl_groups.items():
        if len(matches) < 2:
            continue
        aids = list({str(m.get("analysis_id", "UNKNOWN")) for m in matches})
        dates = [d for d in [_get_date(m) for m in matches] if d]
        qualities = [_get_data_quality(m) for m in matches]
        patterns.append(Pattern(
            pattern_id=_make_pattern_id(PATTERN_RECURRING_WATCHLIST_MATCH, aids + [wl_id]),
            pattern_type=PATTERN_RECURRING_WATCHLIST_MATCH,
            severity="WATCH",
            analysis_ids=aids,
            dates=dates,
            location=None,
            evidence=[f"Watchlist {wl_id} matched {len(matches)} times."],
            count=len(matches),
            data_quality=_worst_quality(qualities),
            limitations=["Watchlist match frequency does not imply trend or cause."],
            explanation=f"Watchlist '{wl_id}' was matched across {len(matches)} evaluations.",
        ))
    return patterns


def detect_repeated_location_alerts(alerts: Sequence[Any]) -> list[Pattern]:
    """Detect repeated alerts for the same location."""
    loc_groups: dict[str, list[dict]] = {}
    for a in alerts:
        ad = _get_record_dict(a)
        loc = _get_location(ad)
        if loc:
            loc_groups.setdefault(loc, []).append(ad)

    patterns = []
    for loc, group in loc_groups.items():
        if len(group) < 2:
            continue
        aids = list({str(ad.get("analysis_id", ad.get("alert_id", "UNKNOWN"))) for ad in group})
        dates = [d for d in [_get_date(ad) for ad in group] if d]
        patterns.append(Pattern(
            pattern_id=_make_pattern_id(PATTERN_REPEATED_LOCATION_ALERTS, aids + [loc]),
            pattern_type=PATTERN_REPEATED_LOCATION_ALERTS,
            severity="ELEVATED" if len(group) >= 3 else "WATCH",
            analysis_ids=aids,
            dates=dates,
            location=loc,
            evidence=[f"{len(group)} alerts observed for location '{loc}'."],
            count=len(group),
            data_quality="HIGH",
            limitations=["Multiple alerts at same location do not indicate a worsening condition."],
            explanation=f"{len(group)} alerts were observed for location '{loc}'.",
        ))
    return patterns


def detect_repeated_signal_type(signals: Sequence[Any]) -> list[Pattern]:
    """Detect repeated signal types across session."""
    type_groups: dict[str, list[dict]] = {}
    for s in signals:
        sd = _get_record_dict(s)
        stype = str(sd.get("signal_type", sd.get("type", "UNKNOWN")))
        type_groups.setdefault(stype, []).append(sd)

    patterns = []
    for stype, group in type_groups.items():
        if len(group) < 2:
            continue
        aids = list({str(sd.get("analysis_id", "UNKNOWN")) for sd in group})
        dates = [d for d in [_get_date(sd) for sd in group] if d]
        qualities = [_get_data_quality(sd) for sd in group]
        patterns.append(Pattern(
            pattern_id=_make_pattern_id(PATTERN_REPEATED_SIGNAL_TYPE, aids + [stype]),
            pattern_type=PATTERN_REPEATED_SIGNAL_TYPE,
            severity="WATCH",
            analysis_ids=aids,
            dates=dates,
            location=None,
            evidence=[f"Signal type '{stype}' observed {len(group)} times."],
            count=len(group),
            data_quality=_worst_quality(qualities),
            limitations=["Repeated signal type is observational, not predictive."],
            explanation=f"Signal type '{stype}' was observed in {len(group)} instances.",
        ))
    return patterns


def detect_data_quality_degradation(records: Sequence[Any]) -> list[Pattern]:
    """Detect declining data quality across sequential analyses."""
    ranked = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "INSUFFICIENT": 0}
    dq_sequence: list[tuple[str, dict]] = []
    for r in records:
        rd = _get_record_dict(r)
        dq = _get_data_quality(rd)
        date = _get_date(rd) or ""
        dq_sequence.append((date, rd))

    if len(dq_sequence) < 2:
        return []

    dq_sequence.sort(key=lambda x: x[0])
    degradation_count = 0
    for i in range(1, len(dq_sequence)):
        prev_dq = _get_data_quality(dq_sequence[i - 1][1])
        curr_dq = _get_data_quality(dq_sequence[i][1])
        if ranked.get(curr_dq, 3) < ranked.get(prev_dq, 3):
            degradation_count += 1

    if degradation_count == 0:
        return []

    aids = [str(rd.get("analysis_id", "UNKNOWN")) for _, rd in dq_sequence]
    dates = [d for d, _ in dq_sequence if d]
    qualities = [_get_data_quality(rd) for _, rd in dq_sequence]

    return [Pattern(
        pattern_id=_make_pattern_id(PATTERN_DATA_QUALITY_DEGRADATION, aids),
        pattern_type=PATTERN_DATA_QUALITY_DEGRADATION,
        severity="WATCH" if degradation_count < 2 else "ELEVATED",
        analysis_ids=aids,
        dates=dates,
        location=None,
        evidence=[f"Data quality decreased in {degradation_count} sequential transition(s)."],
        count=degradation_count,
        data_quality=_worst_quality(qualities),
        limitations=["Data quality changes may reflect input variability, not systemic issues."],
        explanation=f"Data quality decreased across {degradation_count} sequential analysis transition(s).",
    )]


def detect_temperature_direction(records: Sequence[Any]) -> list[Pattern]:
    """Detect consistent temperature direction across sequential analyses."""
    temps: list[tuple[str, float, dict]] = []
    for r in records:
        rd = _get_record_dict(r)
        metrics = rd.get("metrics", {})
        temp = _safe_float(rd.get("observed_temperature")) or _safe_float(metrics.get("mean_temp"))
        date = _get_date(rd) or ""
        if temp is not None:
            temps.append((date, temp, rd))

    if len(temps) < 3:
        return []

    temps.sort(key=lambda x: x[0])
    increasing = all(temps[i][1] <= temps[i + 1][1] for i in range(len(temps) - 1))
    decreasing = all(temps[i][1] >= temps[i + 1][1] for i in range(len(temps) - 1))

    if not increasing and not decreasing:
        return []

    direction = "increased" if increasing else "decreased"
    aids = [str(rd.get("analysis_id", "UNKNOWN")) for _, _, rd in temps]
    dates = [d for d, _, _ in temps if d]
    qualities = [_get_data_quality(rd) for _, _, rd in temps]

    return [Pattern(
        pattern_id=_make_pattern_id(PATTERN_TEMPERATURE_DIRECTION, aids),
        pattern_type=PATTERN_TEMPERATURE_DIRECTION,
        severity="WATCH",
        analysis_ids=aids,
        dates=dates,
        location=None,
        evidence=[f"Temperature {direction} across {len(temps)} sequential analyses ({temps[0][1]}°C → {temps[-1][1]}°C)."],
        count=len(temps),
        data_quality=_worst_quality(qualities),
        limitations=[
            "Sequential temperature direction does not establish trend or causation.",
            "Pattern based on available session data only.",
        ],
        explanation=f"Mean temperature {direction} across the last {len(temps)} comparable analyses.",
    )]


def detect_all_patterns(
    records: Sequence[Any] | None = None,
    signals: Sequence[Any] | None = None,
    alerts: Sequence[Any] | None = None,
    watchlist_evaluations: Sequence[Any] | None = None,
    threshold: float = 35.0,
    high_temp_threshold: float = 33.0,
) -> list[Pattern]:
    """Run all pattern detectors and return combined results."""
    recs = list(records) if records else []
    sigs = list(signals) if signals else []
    als = list(alerts) if alerts else []
    wl_evals = list(watchlist_evaluations) if watchlist_evaluations else []

    patterns: list[Pattern] = []
    patterns.extend(detect_repeated_threshold_exceedance(recs, threshold))
    patterns.extend(detect_repeated_high_temperature(recs, high_temp_threshold))
    patterns.extend(detect_recurring_watchlist_matches(wl_evals))
    patterns.extend(detect_repeated_location_alerts(als))
    patterns.extend(detect_repeated_signal_type(sigs))
    patterns.extend(detect_data_quality_degradation(recs))
    patterns.extend(detect_temperature_direction(recs))
    return patterns
