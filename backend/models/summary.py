"""Normalized analysis metadata and summary models.

Provides a unified, defensive representation of task results for UI rendering
and session tracking without altering or fabricating raw provider data.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class AnalysisSummary(BaseModel):
    """Normalized summary of an analysis task for UI and session tracking."""

    analysis_type: str = Field(..., description="'heatmap' or 'heat_intelligence'")
    activity_id: str = Field(..., description="Unique activity identifier")
    status: str = Field(..., description="Normalized task status (e.g. Completed, Processing, Failed)")
    label: str | None = Field(default=None, description="Human-readable location or description label")
    created_at: str | None = Field(default=None, description="ISO timestamp of creation if known")
    completed_at: str | None = Field(default=None, description="ISO timestamp of completion if known")
    summary_metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Key extracted scalar metrics (e.g. tile_count, mean_temp, date, analysis_dimensions)",
    )
    has_report_download: bool = Field(
        default=False,
        description="Whether a PDF report is available for retrieval",
    )


def extract_analysis_summary(
    analysis_type: str,
    activity_id: str,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    request_payload: dict[str, Any] | None = None,
    label: str | None = None,
) -> AnalysisSummary:
    """Extract a safe, normalized summary from an analysis result without fabricating missing data."""
    summary_metrics: dict[str, Any] = {}
    has_report = False

    if request_payload:
        if "date" in request_payload:
            summary_metrics["date"] = str(request_payload["date"])
        if "temperature" in request_payload:
            summary_metrics["observed_temperature"] = request_payload["temperature"]
        if "analysis" in request_payload and isinstance(request_payload["analysis"], list):
            summary_metrics["analysis_dimensions"] = request_payload["analysis"]
        if "granularity" in request_payload:
            summary_metrics["granularity"] = request_payload["granularity"]

    if result and isinstance(result, dict):
        if analysis_type == "heatmap":
            # Extract tile count and basic stats if map_data or stats_data exists
            map_data = result.get("map_data")
            if isinstance(map_data, dict) and "features" in map_data and isinstance(map_data["features"], list):
                summary_metrics["tile_count"] = len(map_data["features"])
                
            stats_data = result.get("stats_data") or result.get("statistics")
            if isinstance(stats_data, dict):
                temp_stats = stats_data.get("temperature_stats") or stats_data
                if isinstance(temp_stats, dict):
                    if "mean" in temp_stats:
                        summary_metrics["mean_temperature"] = temp_stats["mean"]
                    if "min" in temp_stats:
                        summary_metrics["min_temperature"] = temp_stats["min"]
                    if "max" in temp_stats:
                        summary_metrics["max_temperature"] = temp_stats["max"]

        elif analysis_type in ("heat_intelligence", "heat-intelligence"):
            if "download_link" in result and result["download_link"]:
                has_report = True

    return AnalysisSummary(
        analysis_type=analysis_type,
        activity_id=activity_id,
        status=status,
        label=label,
        summary_metrics=summary_metrics,
        has_report_download=has_report,
    )
