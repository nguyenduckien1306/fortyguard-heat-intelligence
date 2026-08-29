"""Pure Deterministic Scenario Analysis and What-If Exploration Sandbox.

Allows analysts to explore mathematical what-if adjustments on completed AnalysisRecords.

Strict Invariants:
1. Zero mutation of historical AnalysisRecords.
2. Zero persistence to session history records.
3. Zero network I/O, zero provider requests, zero credit consumption.
4. Calculations are purely descriptive mathematical adjustments, NOT forecasts or predictions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Mapping

from frontend.utils.operational_intelligence import _extract_metric_val, _safe_float

SCENARIO_ANALYTICS_DISCLAIMER: str = (
    "Scenario Exploration Notice: This is a purely mathematical what-if calculation based on "
    "user-specified adjustments applied to confirmed historical observations. It does not constitute "
    "a weather forecast, climate projection, predictive simulation, or guarantee of future conditions."
)


@dataclass(frozen=True)
class ScenarioAdjustment:
    """Immutable parameters for a what-if analytical scenario."""

    temperature_delta: float = 0.0  # e.g. +2.0°C or -1.5°C
    threshold_delta: float = 0.0  # e.g. -1.0°C policy adjustment
    spread_delta: float = 0.0  # e.g. +1.5°C
    proportion_delta: float = 0.0  # e.g. +10.0%

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ScenarioAdjustment:
        return cls(
            temperature_delta=_safe_float(data.get("temperature_delta")) or 0.0,
            threshold_delta=_safe_float(data.get("threshold_delta")) or 0.0,
            spread_delta=_safe_float(data.get("spread_delta")) or 0.0,
            proportion_delta=_safe_float(data.get("proportion_delta")) or 0.0,
        )


@dataclass(frozen=True)
class ScenarioComparison:
    """Deterministic comparison between observed analysis state and scenario state."""

    analysis_id: str
    location: str
    observed_mean_temp: float | None
    scenario_mean_temp: float | None
    observed_min_temp: float | None
    scenario_min_temp: float | None
    observed_max_temp: float | None
    scenario_max_temp: float | None
    observed_spread: float | None
    scenario_spread: float | None
    observed_hot_proportion: float | None
    scenario_hot_proportion: float | None
    threshold_observed: float
    threshold_scenario: float
    observed_exceeds_threshold: bool
    scenario_exceeds_threshold: bool
    threshold_delta_exceedance: float | None
    adjustments: ScenarioAdjustment
    narrative_summary: str
    disclaimer: str = SCENARIO_ANALYTICS_DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "location": self.location,
            "observed_mean_temp": self.observed_mean_temp,
            "scenario_mean_temp": self.scenario_mean_temp,
            "observed_min_temp": self.observed_min_temp,
            "scenario_min_temp": self.scenario_min_temp,
            "observed_max_temp": self.observed_max_temp,
            "scenario_max_temp": self.scenario_max_temp,
            "observed_spread": self.observed_spread,
            "scenario_spread": self.scenario_spread,
            "observed_hot_proportion": self.observed_hot_proportion,
            "scenario_hot_proportion": self.scenario_hot_proportion,
            "threshold_observed": self.threshold_observed,
            "threshold_scenario": self.threshold_scenario,
            "observed_exceeds_threshold": self.observed_exceeds_threshold,
            "scenario_exceeds_threshold": self.scenario_exceeds_threshold,
            "threshold_delta_exceedance": self.threshold_delta_exceedance,
            "adjustments": self.adjustments.to_dict(),
            "narrative_summary": self.narrative_summary,
            "disclaimer": self.disclaimer,
        }


def create_scenario_adjustments(
    temperature_delta: float = 0.0,
    threshold_delta: float = 0.0,
    spread_delta: float = 0.0,
    proportion_delta: float = 0.0,
) -> ScenarioAdjustment:
    """Create a validated, immutable ScenarioAdjustment."""
    t_adj = _safe_float(temperature_delta) or 0.0
    th_adj = _safe_float(threshold_delta) or 0.0
    s_adj = _safe_float(spread_delta) or 0.0
    p_adj = _safe_float(proportion_delta) or 0.0

    return ScenarioAdjustment(
        temperature_delta=round(t_adj, 2),
        threshold_delta=round(th_adj, 2),
        spread_delta=round(s_adj, 2),
        proportion_delta=round(p_adj, 2),
    )


def calculate_scenario_metrics(
    record: Any,
    adjustments: ScenarioAdjustment,
) -> dict[str, Any]:
    """Calculate what-if adjusted metrics for an AnalysisRecord without mutating it."""
    r_dict = record.to_dict() if hasattr(record, "to_dict") else dict(record)

    mean_obs = _extract_metric_val(r_dict, ["mean_temp", "mean_temperature", "observed_temperature", "temperature"])
    min_obs = _extract_metric_val(r_dict, ["min_temp", "min_temperature"])
    max_obs = _extract_metric_val(r_dict, ["max_temp", "max_temperature"])
    spread_obs = _extract_metric_val(r_dict, ["temp_spread", "temperature_spread", "spread"])
    prop_obs = _extract_metric_val(r_dict, ["above_threshold_proportion", "hot_tile_pct"])

    # Calculate scenario values
    mean_scen = round(mean_obs + adjustments.temperature_delta, 2) if mean_obs is not None else None
    min_scen = round(min_obs + adjustments.temperature_delta, 2) if min_obs is not None else None
    max_scen = round(max_obs + adjustments.temperature_delta, 2) if max_obs is not None else None

    spread_scen = round(max(0.0, spread_obs + adjustments.spread_delta), 2) if spread_obs is not None else None

    # Proportion adjusted (clamped 0 to 100%)
    if prop_obs is not None:
        norm_prop = prop_obs if prop_obs > 1.0 else prop_obs * 100.0
        prop_scen = round(max(0.0, min(100.0, norm_prop + adjustments.proportion_delta)), 2)
    else:
        prop_scen = None

    return {
        "mean_temperature": mean_scen,
        "min_temperature": min_scen,
        "max_temperature": max_scen,
        "temperature_spread": spread_scen,
        "above_threshold_proportion": prop_scen,
    }


def compare_scenario_to_observed(
    record: Any,
    adjustments: ScenarioAdjustment,
    base_threshold: float = 35.0,
) -> ScenarioComparison:
    """Compare observed record metrics against scenario adjustments."""
    r_dict = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    aid = str(r_dict.get("analysis_id") or r_dict.get("activity_id") or "UNKNOWN")
    loc = str(r_dict.get("location_label") or "Analysis Area")

    mean_obs = _extract_metric_val(r_dict, ["mean_temp", "mean_temperature", "observed_temperature", "temperature"])
    min_obs = _extract_metric_val(r_dict, ["min_temp", "min_temperature"])
    max_obs = _extract_metric_val(r_dict, ["max_temp", "max_temperature"])
    spread_obs = _extract_metric_val(r_dict, ["temp_spread", "temperature_spread", "spread"])
    prop_obs = _extract_metric_val(r_dict, ["above_threshold_proportion", "hot_tile_pct"])

    scen_metrics = calculate_scenario_metrics(record, adjustments)

    thresh_obs = round(base_threshold, 2)
    thresh_scen = round(base_threshold + adjustments.threshold_delta, 2)

    # Threshold evaluation
    obs_val_for_thresh = mean_obs if mean_obs is not None else max_obs
    scen_val_for_thresh = scen_metrics["mean_temperature"] if scen_metrics["mean_temperature"] is not None else scen_metrics["max_temperature"]

    obs_exceeds = (obs_val_for_thresh >= thresh_obs) if obs_val_for_thresh is not None else False
    scen_exceeds = (scen_val_for_thresh >= thresh_scen) if scen_val_for_thresh is not None else False

    thresh_delta_exceedance = round(scen_val_for_thresh - thresh_scen, 2) if scen_val_for_thresh is not None else None

    # Narrative generation (strictly descriptive mathematical text)
    narrative_parts: list[str] = []
    if mean_obs is not None and scen_metrics["mean_temperature"] is not None:
        adj_str = f"{adjustments.temperature_delta:+.1f}°C"
        narrative_parts.append(
            f"Under a hypothetical {adj_str} temperature adjustment, observed mean temperature of {mean_obs:.1f}°C becomes {scen_metrics['mean_temperature']:.1f}°C."
        )

    if scen_exceeds and not obs_exceeds:
        narrative_parts.append(
            f"This adjustment shifts the scenario temperature above the adjusted threshold ({thresh_scen:.1f}°C)."
        )
    elif not scen_exceeds and obs_exceeds:
        narrative_parts.append(
            f"This adjustment brings the scenario temperature below the adjusted threshold ({thresh_scen:.1f}°C)."
        )
    elif scen_exceeds and obs_exceeds:
        narrative_parts.append(
            f"Both observed and scenario states exceed their respective thresholds ({thresh_obs:.1f}°C and {thresh_scen:.1f}°C)."
        )
    else:
        narrative_parts.append(
            f"Both observed and scenario states remain within their respective thresholds ({thresh_obs:.1f}°C and {thresh_scen:.1f}°C)."
        )

    narrative_summary = " ".join(narrative_parts)

    return ScenarioComparison(
        analysis_id=aid,
        location=loc,
        observed_mean_temp=mean_obs,
        scenario_mean_temp=scen_metrics["mean_temperature"],
        observed_min_temp=min_obs,
        scenario_min_temp=scen_metrics["min_temperature"],
        observed_max_temp=max_obs,
        scenario_max_temp=scen_metrics["max_temperature"],
        observed_spread=spread_obs,
        scenario_spread=scen_metrics["temperature_spread"],
        observed_hot_proportion=prop_obs,
        scenario_hot_proportion=scen_metrics["above_threshold_proportion"],
        threshold_observed=thresh_obs,
        threshold_scenario=thresh_scen,
        observed_exceeds_threshold=obs_exceeds,
        scenario_exceeds_threshold=scen_exceeds,
        threshold_delta_exceedance=thresh_delta_exceedance,
        adjustments=adjustments,
        narrative_summary=narrative_summary,
        disclaimer=SCENARIO_ANALYTICS_DISCLAIMER,
    )
