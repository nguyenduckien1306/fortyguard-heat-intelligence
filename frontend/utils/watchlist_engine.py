"""Pure Deterministic Watchlist Evaluation Engine.

Evaluates Watchlist criteria against completed AnalysisRecords in O(N) time.

Strict Invariants:
1. Zero HTTP / Network I/O.
2. Pure mathematical evaluation — no mutation of source records.
3. Distinguishes missing/insufficient data from zero.
4. Respects temporal comparison modes (PREVIOUS, FIRST, ROLLING).
5. Applies anti-flapping hysteresis where configured.
6. Strictly non-causal language and transparent data quality classification.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import math
from typing import Any, Mapping, Sequence

from frontend.utils.clock import Clock, get_current_clock
from frontend.utils.operational_intelligence import (
    _determine_record_data_quality,
    _extract_metric_val,
    _safe_float,
)
from frontend.utils.watchlists import Watchlist, WatchlistCriterion

TOLERANCE: float = 1e-6


@dataclass(frozen=True)
class CriterionEvaluationResult:
    """Evaluation result for a single Watchlist criterion."""

    metric: str
    operator: str
    threshold: float
    matched: bool
    observed_value: float | None
    has_data: bool
    evidence: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WatchlistEvaluation:
    """Complete evaluation outcome for a Watchlist against completed session records."""

    eval_id: str
    watchlist_id: str
    watchlist_name: str
    watchlist_version: int
    evaluated_at: str
    matched: bool
    criterion_results: list[CriterionEvaluationResult] = field(default_factory=list)
    matched_criteria: list[str] = field(default_factory=list)
    unmatched_criteria: list[str] = field(default_factory=list)
    insufficient_data_criteria: list[str] = field(default_factory=list)
    baseline_analysis_id: str | None = None
    comparison_analysis_id: str | None = None
    observed_values: dict[str, float | None] = field(default_factory=dict)
    threshold_values: dict[str, float] = field(default_factory=dict)
    delta: float | None = None
    percent_delta: float | None = None
    data_quality: str = "HIGH"  # "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT"
    evidence_list: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["criterion_results"] = [c.to_dict() if isinstance(c, CriterionEvaluationResult) else dict(c) for c in self.criterion_results]
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WatchlistEvaluation:
        raw_res = data.get("criterion_results", [])
        c_results = [CriterionEvaluationResult(**c) if isinstance(c, Mapping) else c for c in raw_res]
        return cls(
            eval_id=str(data.get("eval_id", "")),
            watchlist_id=str(data.get("watchlist_id", "")),
            watchlist_name=str(data.get("watchlist_name", "")),
            watchlist_version=int(data.get("watchlist_version", 1)),
            evaluated_at=str(data.get("evaluated_at", "")),
            matched=bool(data.get("matched", False)),
            criterion_results=c_results,
            matched_criteria=list(data.get("matched_criteria", [])),
            unmatched_criteria=list(data.get("unmatched_criteria", [])),
            insufficient_data_criteria=list(data.get("insufficient_data_criteria", [])),
            baseline_analysis_id=data.get("baseline_analysis_id"),
            comparison_analysis_id=data.get("comparison_analysis_id"),
            observed_values=dict(data.get("observed_values", {})),
            threshold_values=dict(data.get("threshold_values", {})),
            delta=_safe_float(data.get("delta")),
            percent_delta=_safe_float(data.get("percent_delta")),
            data_quality=str(data.get("data_quality", "HIGH")),
            evidence_list=list(data.get("evidence_list", [])),
            limitations=list(data.get("limitations", [])),
        )


def _eval_operator(observed: float, operator: str, threshold: float, tolerance: float = TOLERANCE) -> bool:
    """Evaluate numeric comparison deterministically with float tolerance."""
    if operator == ">":
        return observed > threshold + tolerance
    elif operator == ">=":
        return observed >= threshold - tolerance
    elif operator == "<":
        return observed < threshold - tolerance
    elif operator == "<=":
        return observed <= threshold + tolerance
    elif operator == "==":
        return abs(observed - threshold) <= tolerance
    elif operator == "!=":
        return abs(observed - threshold) > tolerance
    return False


def _filter_and_sort_scoped_records(records: Sequence[Any], location_scope: str, analysis_type_scope: str) -> list[dict[str, Any]]:
    """Filter records matching scope and sort chronologically (oldest to newest)."""
    scoped: list[dict[str, Any]] = []

    for r in records:
        r_dict = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        status_val = str(r_dict.get("status", "")).strip().capitalize()
        if status_val != "Completed":
            continue

        # Location scope
        r_loc = str(r_dict.get("location_label", "")).strip()
        if location_scope != "all" and location_scope.lower() not in r_loc.lower():
            continue

        # Analysis type scope
        r_type = str(r_dict.get("analysis_type", "")).strip().lower()
        if analysis_type_scope != "all":
            if analysis_type_scope.lower() not in r_type:
                continue

        scoped.append(r_dict)

    # Sort chronologically by date/created_at
    def sort_key(d: dict[str, Any]) -> str:
        return str(d.get("date") or d.get("created_at") or "")

    return sorted(scoped, key=sort_key)


def evaluate_watchlist(
    watchlist: Watchlist,
    records: Sequence[Any],
    clock: Clock | None = None,
) -> WatchlistEvaluation:
    """Evaluate a single Watchlist against completed session records deterministically."""
    clk = clock or get_current_clock()
    now_iso = clk.now_iso()

    eval_seed = f"{watchlist.watchlist_id}_{watchlist.version}_{now_iso}_{len(records)}"
    eval_id = f"EV-{hashlib.sha256(eval_seed.encode('utf-8')).hexdigest()[:10]}"

    if not watchlist.enabled:
        return WatchlistEvaluation(
            eval_id=eval_id,
            watchlist_id=watchlist.watchlist_id,
            watchlist_name=watchlist.name,
            watchlist_version=watchlist.version,
            evaluated_at=now_iso,
            matched=False,
            data_quality="INSUFFICIENT",
            limitations=["Watchlist is currently disabled."],
        )

    scoped_records = _filter_and_sort_scoped_records(
        records,
        location_scope=watchlist.location_scope,
        analysis_type_scope=watchlist.analysis_type_scope,
    )

    if not scoped_records:
        return WatchlistEvaluation(
            eval_id=eval_id,
            watchlist_id=watchlist.watchlist_id,
            watchlist_name=watchlist.name,
            watchlist_version=watchlist.version,
            evaluated_at=now_iso,
            matched=False,
            data_quality="INSUFFICIENT",
            insufficient_data_criteria=[c.metric for c in watchlist.criteria],
            limitations=["No completed analyses matching watchlist scope found in session."],
        )

    latest_rec = scoped_records[-1]
    comparison_id = str(latest_rec.get("analysis_id", ""))
    baseline_id: str | None = None

    # Determine Baseline Record based on comparison_mode
    baseline_rec: dict[str, Any] | None = None
    if len(scoped_records) >= 2:
        if watchlist.comparison_mode == "FIRST":
            baseline_rec = scoped_records[0]
        elif watchlist.comparison_mode == "ROLLING":
            # Window of previous records up to window_size
            window = scoped_records[:-1][-watchlist.window_size:]
            baseline_rec = window[0] if len(window) == 1 else None  # Specific anchor
        else:  # PREVIOUS default
            baseline_rec = scoped_records[-2]

        if baseline_rec:
            baseline_id = str(baseline_rec.get("analysis_id", ""))

    # Evaluate Each Criterion
    criterion_results: list[CriterionEvaluationResult] = []
    matched_criteria: list[str] = []
    unmatched_criteria: list[str] = []
    insufficient_criteria: list[str] = []
    observed_values: dict[str, float | None] = {}
    threshold_values: dict[str, float] = {}
    evidence_list: list[str] = []
    limitations: list[str] = []

    overall_dq = _determine_record_data_quality(latest_rec)
    calculated_delta: float | None = None
    calculated_pct_delta: float | None = None

    for crit in watchlist.criteria:
        threshold_values[crit.metric] = crit.threshold
        obs_val: float | None = None
        has_data = False
        matched = False
        evidence_str = ""
        notes_str = ""

        # 1. mean_temperature
        if crit.metric == "mean_temperature":
            obs_val = _extract_metric_val(latest_rec, ["mean_temp", "mean_temperature", "observed_temperature", "temperature"])
            if obs_val is not None:
                has_data = True
                # Check hysteresis: if trigger_threshold is configured, use it for matching
                effective_threshold = crit.trigger_threshold if crit.trigger_threshold is not None else crit.threshold
                matched = _eval_operator(obs_val, crit.operator, effective_threshold, crit.tolerance)
                evidence_str = f"Observed mean temperature {obs_val:.2f}°C {crit.operator} threshold {crit.threshold:.2f}°C."
            else:
                notes_str = "Mean temperature metric unavailable in latest analysis."

        # 2. temperature_spread
        elif crit.metric == "temperature_spread":
            obs_val = _extract_metric_val(latest_rec, ["temp_spread", "temperature_spread", "spread"])
            if obs_val is not None:
                has_data = True
                matched = _eval_operator(obs_val, crit.operator, crit.threshold, crit.tolerance)
                evidence_str = f"Observed temperature spread {obs_val:.2f}°C {crit.operator} threshold {crit.threshold:.2f}°C."
            else:
                notes_str = "Temperature spread metric unavailable in latest analysis."

        # 3. above_threshold_proportion
        elif crit.metric == "above_threshold_proportion":
            obs_val = _extract_metric_val(latest_rec, ["above_threshold_proportion", "hot_tile_pct"])
            if obs_val is not None:
                has_data = True
                # Normalize decimal (0.45) to percentage (45.0) if threshold is > 1.0
                if obs_val <= 1.0 and crit.threshold > 1.0:
                    obs_val = obs_val * 100.0
                matched = _eval_operator(obs_val, crit.operator, crit.threshold, crit.tolerance)
                evidence_str = f"Observed hot area proportion {obs_val:.1f}% {crit.operator} threshold {crit.threshold:.1f}%."
            else:
                notes_str = "Above threshold proportion metric unavailable in latest analysis."

        # 4. analysis_count
        elif crit.metric == "analysis_count":
            count_val = float(len(scoped_records))
            obs_val = count_val
            has_data = True
            matched = _eval_operator(count_val, crit.operator, crit.threshold, crit.tolerance)
            evidence_str = f"Evaluated completed analysis count {int(count_val)} {crit.operator} threshold {int(crit.threshold)}."

        # 5. temperature_change
        elif crit.metric == "temperature_change":
            if len(scoped_records) < 2:
                notes_str = "Requires at least 2 completed analyses for temporal temperature change."
            else:
                latest_m = _extract_metric_val(latest_rec, ["mean_temp", "mean_temperature", "observed_temperature"])
                if watchlist.comparison_mode == "ROLLING":
                    window = scoped_records[:-1][-watchlist.window_size:]
                    baseline_vals = [
                        _extract_metric_val(w, ["mean_temp", "mean_temperature", "observed_temperature"])
                        for w in window
                    ]
                    valid_bases = [v for v in baseline_vals if v is not None]
                    baseline_m = sum(valid_bases) / len(valid_bases) if valid_bases else None
                else:
                    baseline_m = _extract_metric_val(baseline_rec, ["mean_temp", "mean_temperature", "observed_temperature"]) if baseline_rec else None

                if latest_m is not None and baseline_m is not None:
                    has_data = True
                    diff = latest_m - baseline_m
                    obs_val = round(diff, 4)
                    calculated_delta = obs_val
                    matched = _eval_operator(obs_val, crit.operator, crit.threshold, crit.tolerance)
                    evidence_str = f"Observed temperature delta {obs_val:+.2f}°C (Latest: {latest_m:.2f}°C, Baseline: {baseline_m:.2f}°C) {crit.operator} threshold {crit.threshold:+.2f}°C."
                else:
                    notes_str = "Temperature metric missing in baseline or latest record."

        # 6. temperature_change_percent
        elif crit.metric == "temperature_change_percent":
            if len(scoped_records) < 2:
                notes_str = "Requires at least 2 completed analyses for percentage change."
            else:
                latest_m = _extract_metric_val(latest_rec, ["mean_temp", "mean_temperature", "observed_temperature"])
                baseline_m = _extract_metric_val(baseline_rec, ["mean_temp", "mean_temperature", "observed_temperature"]) if baseline_rec else None

                if latest_m is not None and baseline_m is not None:
                    if abs(baseline_m) > 1e-6:
                        has_data = True
                        pct = ((latest_m - baseline_m) / abs(baseline_m)) * 100.0
                        obs_val = round(pct, 4)
                        calculated_pct_delta = obs_val
                        matched = _eval_operator(obs_val, crit.operator, crit.threshold, crit.tolerance)
                        evidence_str = f"Observed temperature percent change {obs_val:+.1f}% {crit.operator} threshold {crit.threshold:+.1f}%."
                    else:
                        notes_str = "Baseline temperature is zero; cannot compute percentage change."
                else:
                    notes_str = "Temperature metric missing in baseline or latest record."

        observed_values[crit.metric] = obs_val

        if not has_data:
            insufficient_criteria.append(crit.metric)
            if notes_str:
                limitations.append(notes_str)
        elif matched:
            matched_criteria.append(crit.metric)
            if evidence_str:
                evidence_list.append(evidence_str)
        else:
            unmatched_criteria.append(crit.metric)

        criterion_results.append(CriterionEvaluationResult(
            metric=crit.metric,
            operator=crit.operator,
            threshold=crit.threshold,
            matched=matched,
            observed_value=obs_val,
            has_data=has_data,
            evidence=evidence_str,
            notes=notes_str,
        ))

    # All criteria with data must match, and there must be at least one matching criterion without missing data
    overall_matched = (
        len(matched_criteria) > 0
        and len(unmatched_criteria) == 0
        and len(insufficient_criteria) == 0
    )

    if insufficient_criteria:
        overall_dq = "LOW" if overall_dq == "HIGH" else "INSUFFICIENT"

    return WatchlistEvaluation(
        eval_id=eval_id,
        watchlist_id=watchlist.watchlist_id,
        watchlist_name=watchlist.name,
        watchlist_version=watchlist.version,
        evaluated_at=now_iso,
        matched=overall_matched,
        criterion_results=criterion_results,
        matched_criteria=matched_criteria,
        unmatched_criteria=unmatched_criteria,
        insufficient_data_criteria=insufficient_criteria,
        baseline_analysis_id=baseline_id,
        comparison_analysis_id=comparison_id,
        observed_values=observed_values,
        threshold_values=threshold_values,
        delta=calculated_delta,
        percent_delta=calculated_pct_delta,
        data_quality=overall_dq,
        evidence_list=evidence_list,
        limitations=limitations,
    )


def evaluate_all_watchlists(
    watchlists: Sequence[Watchlist],
    records: Sequence[Any],
    clock: Clock | None = None,
) -> list[WatchlistEvaluation]:
    """Evaluate all configured Watchlists against completed session records in a single pass."""
    return [evaluate_watchlist(wl, records, clock=clock) for wl in watchlists]
