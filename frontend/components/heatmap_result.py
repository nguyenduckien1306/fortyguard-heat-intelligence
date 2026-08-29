"""Composes the full analytical display of a completed Heatmap result."""

from __future__ import annotations

from typing import Any, Mapping

import streamlit as st
from pydantic import ValidationError

from backend.models.heatmap_result import parse_heatmap_result
from frontend.components.map_view import render_heatmap_result_map
from frontend.components.metrics import render_result_statistics
from frontend.utils.colors import compute_temperature_bounds
from frontend.utils.export import (
    generate_analysis_export_json,
    generate_analysis_export_text,
    sanitize_raw_result_for_inspection,
)
from frontend.utils.heatmap import is_polygon_feature_collection
from frontend.utils.heatmap_analytics import compute_tile_metrics, get_heatmap_data_quality_report
from frontend.utils.insights import (
    ANALYTICS_DISCLAIMER,
    generate_heatmap_insights,
    insight_severity_to_icon,
)


def render_heatmap_result(
    polygon_aoi: Mapping[str, Any] | None,
    result: dict[str, Any] | None,
    activity_id: str | None = None,
    request_params: Mapping[str, Any] | None = None,
) -> None:
    """
    Render the comprehensive analytical dashboard for a completed Heatmap result.

    Never raises: an unexpected/malformed result falls back to a safe
    notice plus the untouched raw payload instead of crashing the page.
    """
    if not result:
        st.info("This task completed with no result payload.")
        return

    try:
        parsed = parse_heatmap_result(result)
    except (ValidationError, TypeError, ValueError, AttributeError):
        st.warning(
            "The result payload could not be interpreted. Showing the raw data instead."
        )
        with st.expander("Raw result", expanded=True):
            st.json(sanitize_raw_result_for_inspection(result))
        return

    if parsed is None:
        st.info("This task completed with no result payload.")
        return

    # ── Section 0: High-Level Analytical Summary ──
    derived_metrics = _render_heatmap_summary_card(parsed)

    st.divider()

    # ── Section 0.5: Analytical Insights ──
    _render_analytical_insights(parsed.map_data, derived_metrics)

    st.divider()

    # ── Section 1: Visualization Mode & Map Layer ──
    color_mode_options = {
        "Average Temperature": "average_temperature",
        "Minimum Temperature": "min_temperature",
        "Maximum Temperature": "max_temperature",
    }
    col_mode, col_space = st.columns([2, 3])
    with col_mode:
        selected_mode_label = st.radio(
            "Color map tiles by:",
            options=list(color_mode_options.keys()),
            index=0,
            horizontal=True,
            key=f"_heatmap_color_mode_{activity_id or 'default'}",
        )
    property_key = color_mode_options[selected_mode_label]

    render_heatmap_result_map(polygon_aoi, parsed.map_data, property_key=property_key)

    st.divider()

    # ── Section 2: Data Quality & Extremes ──
    _render_data_quality_and_extremes(parsed.map_data, derived_metrics)

    st.divider()

    # ── Section 3: Structured Analytics & Charts ──
    render_result_statistics(parsed.statistics)

    st.divider()

    # ── Section 4: Export Local Summary ──
    _render_export_section(
        activity_id=activity_id,
        request_params=request_params,
        derived_metrics=derived_metrics,
        result=result,
    )

    st.divider()

    # ── Section 5: Metadata & Quota ──
    st.subheader("Metadata & Quota")
    if parsed.metadata:
        st.json(parsed.metadata)
    else:
        st.caption("Metadata and credit usage were not provided by the FortyGuard API response.")

    # ── Section 6: Developer Raw Payload Inspection ──
    with st.expander("Developer / Raw Provider Response", expanded=False):
        st.json(sanitize_raw_result_for_inspection(parsed.raw))


def _render_heatmap_summary_card(parsed) -> dict[str, Any]:
    """Render a high-level summary card with dynamic tile counts and temperature metrics."""
    tile_metrics = compute_tile_metrics(parsed.map_data)
    tile_count = tile_metrics["total_tiles"]
    min_temp = tile_metrics["min_temp"]
    max_temp = tile_metrics["max_temp"]
    mean_temp = tile_metrics["mean_temp"]
    temp_spread = tile_metrics["temp_spread"]

    # Fallback to stats_data if map_data metrics are missing
    if isinstance(parsed.statistics, Mapping):
        tstats = parsed.statistics.get("temperature_stats")
        if isinstance(tstats, Mapping):
            if mean_temp is None:
                mean_temp = tstats.get("mean")
            if min_temp is None:
                min_temp = tstats.get("min") if tstats.get("min") is not None else tstats.get("minimum")
            if max_temp is None:
                max_temp = tstats.get("max") if tstats.get("max") is not None else tstats.get("maximum")
            if temp_spread is None and max_temp is not None and min_temp is not None:
                temp_spread = max_temp - min_temp

    min_str = f"{min_temp:.2f} °C" if min_temp is not None else "N/A"
    max_str = f"{max_temp:.2f} °C" if max_temp is not None else "N/A"
    range_str = f"{min_str} — {max_str}" if (min_temp is not None and max_temp is not None) else "N/A"
    mean_str = f"{mean_temp:.2f} °C" if mean_temp is not None else "N/A"
    spread_str = f"{temp_spread:.2f} °C" if temp_spread is not None else "N/A"
    tiles_str = f"{tile_count}"

    st.markdown("### Heatmap Analysis Complete")
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"**Spatial Tiles**<br/><span style='font-size: 16px; font-weight: 600;'>{tiles_str}</span>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"**Temperature Range**<br/><span style='font-size: 16px; font-weight: 600;'>{range_str}</span>", unsafe_allow_html=True)
        with c3:
            st.markdown(f"**Mean Temperature**<br/><span style='font-size: 16px; font-weight: 600;'>{mean_str}</span>", unsafe_allow_html=True)
        with c4:
            st.markdown(f"**Thermal Spread (Δ)**<br/><span style='font-size: 16px; font-weight: 600;'>{spread_str}</span>", unsafe_allow_html=True)

    return {
        "tile_count": tile_count,
        "min_temp": min_temp,
        "max_temp": max_temp,
        "mean_temp": mean_temp,
        "temp_spread": temp_spread,
    }


def _render_data_quality_and_extremes(map_data: Any, derived_metrics: dict[str, Any]) -> None:
    """Render data quality check and hottest/coolest tile highlights."""
    st.subheader("Spatial Analytics & Data Quality")
    col_dq, col_ext = st.columns(2)

    quality_report = get_heatmap_data_quality_report(map_data)
    tile_metrics = compute_tile_metrics(map_data)

    with col_dq:
        with st.container(border=True):
            st.markdown("##### Data Quality")
            total = quality_report["total_tiles"]
            valid = quality_report["valid_tiles"]
            if quality_report["is_complete"]:
                st.success(f"✓ Complete data: Temperature available for **{valid}/{total}** tiles.")
            elif total > 0:
                st.warning(f"⚠️ Partial data: **{valid}/{total}** tiles have valid temperature values.")
            else:
                st.info("No spatial tile features present.")

            for note in quality_report["notes"]:
                st.caption(f"• {note}")

    with col_ext:
        with st.container(border=True):
            st.markdown("##### Thermal Extremes")
            hottest = tile_metrics.get("hottest_tile")
            coolest = tile_metrics.get("coolest_tile")
            if hottest and coolest:
                st.markdown(f"**Hottest Tile:** Tile `{hottest['tile_id']}` — **{hottest['temperature']:.2f} °C**")
                st.markdown(f"**Coolest Tile:** Tile `{coolest['tile_id']}` — **{coolest['temperature']:.2f} °C**")
            else:
                st.caption("Thermal extremes are not available for this dataset.")


def _render_export_section(
    activity_id: str | None,
    request_params: Mapping[str, Any] | None,
    derived_metrics: dict[str, Any],
    result: dict[str, Any] | None,
) -> None:
    """Render export buttons for local summary reports."""
    st.subheader("Export Local Analysis Summary")
    st.caption("Download a locally generated structured summary report of this analysis.")

    entry_data = {
        "analysis_type": "Heatmap",
        "activity_id": activity_id or "unassigned",
        "status": "Completed",
        "label": request_params.get("location_label", "Heatmap Analysis") if request_params else "Heatmap Analysis",
        "created_at": "Current Session",
        "updated_at": "Current Session",
        "request_params": request_params,
        "metrics_summary": derived_metrics,
    }

    json_str = generate_analysis_export_json(entry_data)
    text_str = generate_analysis_export_text(entry_data)

    c1, c2, c3 = st.columns([2, 2, 3])
    with c1:
        st.download_button(
            label="Download Summary (JSON)",
            data=json_str,
            file_name=f"heatmap_summary_{activity_id or 'local'}.json",
            mime="application/json",
            key=f"_dl_hm_json_{activity_id or 'local'}",
        )
    with c2:
        st.download_button(
            label="Download Summary (TXT)",
            data=text_str,
            file_name=f"heatmap_summary_{activity_id or 'local'}.txt",
            mime="text/plain",
            key=f"_dl_hm_txt_{activity_id or 'local'}",
        )


def _render_analytical_insights(map_data: Any, derived_metrics: dict[str, Any]) -> None:
    """Render the Analytical Insights section derived from tile metrics.

    Every insight traces to actual values. No causality, safety, or
    domain-expertise claims are made.
    """
    st.subheader("Analytical Insights")

    tile_metrics = compute_tile_metrics(map_data)
    quality_report = get_heatmap_data_quality_report(map_data)
    insights = generate_heatmap_insights(tile_metrics, quality_report)

    if not insights:
        st.info("No analytical insights available for this dataset.")
        return

    with st.container(border=True):
        for ins in insights:
            icon = insight_severity_to_icon(ins.severity)
            st.markdown(f"{icon} **{ins.title}** — {ins.summary}")
            if ins.evidence:
                st.caption(f"Evidence: {ins.evidence}")

    st.caption(ANALYTICS_DISCLAIMER)
