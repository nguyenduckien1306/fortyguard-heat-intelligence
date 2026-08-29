"""Sidebar controls with a human-friendly polygon coordinate builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
import json
from typing import Any

import streamlit as st

from frontend.utils.heatmap import (
    DEFAULT_POLYGON_POINTS,
    build_polygon_geojson_from_points,
)
from frontend.utils.validation import (
    validate_geojson_polygon_aoi,
    validate_latitude,
    validate_longitude,
)


@dataclass
class SidebarSelections:
    """User selections from the sidebar."""

    location_label: str
    aoi_description: str
    selected_date: date
    selected_time: time
    granularity: int
    generate_clicked: bool
    polygon_aoi: dict[str, Any] | None = None
    aoi_error: str | None = None


def render_sidebar() -> SidebarSelections:
    """Render human-friendly polygon builder sidebar and return user selections."""
    st.sidebar.markdown("### Analysis Controls")

    location_label = st.sidebar.text_input(
        "Location label (optional)",
        value="Example polygon",
        key="_sidebar_loc_label",
        help="Optional descriptive label for this analysis area.",
    )

    # ── Human-Friendly Polygon Coordinate Builder ──
    st.sidebar.markdown("##### Area of Interest (Polygon Points)")

    # Initialize session state for polygon points if not present or empty
    if (
        "_polygon_points" not in st.session_state
        or not isinstance(st.session_state["_polygon_points"], list)
        or len(st.session_state["_polygon_points"]) == 0
    ):
        st.session_state["_polygon_points"] = [dict(p) for p in DEFAULT_POLYGON_POINTS]

    points: list[dict[str, float]] = st.session_state["_polygon_points"]

    point_errors: list[str] = []
    to_remove: int | None = None

    # Render each coordinate row (Latitude, Longitude, Remove button)
    for idx, pt in enumerate(points):
        col_lat, col_lon, col_rm = st.sidebar.columns([5, 5, 2])
        with col_lat:
            lat_val = st.number_input(
                f"Lat {idx + 1}",
                value=float(pt.get("lat", 40.7050)),
                format="%.4f",
                step=0.001,
                key=f"_pt_lat_{idx}",
                label_visibility="visible" if idx == 0 else "collapsed",
            )
            pt["lat"] = lat_val
            is_lat_ok, lat_err = validate_latitude(lat_val)
            if not is_lat_ok and lat_err:
                point_errors.append(f"Point {idx + 1}: {lat_err}")
                st.caption(f":red[Point {idx + 1}: {lat_err}]")

        with col_lon:
            lon_val = st.number_input(
                f"Lon {idx + 1}",
                value=float(pt.get("lon", -74.0170)),
                format="%.4f",
                step=0.001,
                key=f"_pt_lon_{idx}",
                label_visibility="visible" if idx == 0 else "collapsed",
            )
            pt["lon"] = lon_val
            is_lon_ok, lon_err = validate_longitude(lon_val)
            if not is_lon_ok and lon_err:
                point_errors.append(f"Point {idx + 1}: {lon_err}")
                st.caption(f":red[Point {idx + 1}: {lon_err}]")

        with col_rm:
            if idx == 0:
                st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
            if st.button("✕", key=f"_pt_rm_{idx}", help=f"Remove Point {idx + 1}"):
                to_remove = idx

    # Handle point removal
    if to_remove is not None and len(points) > 0:
        points.pop(to_remove)
        st.session_state["_polygon_points"] = points
        st.rerun()

    # Add Point Button
    if st.sidebar.button("+ Add Point", key="_sidebar_add_pt_btn"):
        last_pt = points[-1] if points else {"lat": 40.7100, "lon": -74.0100}
        points.append({
            "lat": round(float(last_pt.get("lat", 40.71)) + 0.003, 4),
            "lon": round(float(last_pt.get("lon", -74.01)) + 0.003, 4),
        })
        st.session_state["_polygon_points"] = points
        st.rerun()

    # ── Internal Conversion: Points → Valid GeoJSON Polygon ──
    polygon_aoi: dict[str, Any] | None = None
    aoi_error: str | None = None

    if len(points) < 3:
        aoi_error = "Polygon requires at least 3 points."
    elif point_errors:
        aoi_error = point_errors[0]
    else:
        try:
            polygon_aoi = build_polygon_geojson_from_points(points)
            val_res = validate_geojson_polygon_aoi(polygon_aoi)
            if not val_res.is_valid:
                aoi_error = val_res.errors[0] if val_res.errors else "Invalid polygon structure."
        except (ValueError, TypeError) as exc:
            aoi_error = str(exc)

    # Display compact polygon status badge
    if aoi_error:
        st.sidebar.caption(f":red[⚠️ {aoi_error}]")
    else:
        st.sidebar.caption(f"✓ Valid polygon ({len(points)} points)")

    # Developer inspection (collapsed by default)
    with st.sidebar.expander("▸ Developer Details (Generated GeoJSON)", expanded=False):
        st.caption("Auto-generated GeoJSON FeatureCollection passed to FortyGuard Heatmap pipeline:")
        if polygon_aoi:
            st.json(polygon_aoi)
        else:
            st.caption("Invalid polygon state — no GeoJSON generated.")

    # ── Date & Time Controls ──
    st.sidebar.markdown("**Date & Time**")
    col_d, col_t = st.sidebar.columns(2)
    with col_d:
        selected_date = st.date_input("Date", value=date.today(), key="_sidebar_date")
    with col_t:
        selected_time = st.time_input("Time", value=time(14, 0), key="_sidebar_time")

    granularity = st.sidebar.number_input(
        "Granularity (m)",
        min_value=1,
        value=100,
        step=10,
        key="_sidebar_granularity",
        help="Spatial granularity in meters for heatmap generation.",
    )

    generate_clicked = st.sidebar.button(
        "Submit Heatmap",
        type="primary",
        disabled=aoi_error is not None,
        key="_sidebar_submit_btn",
    )

    aoi_description = json.dumps(polygon_aoi, indent=2) if polygon_aoi is not None else ""

    return SidebarSelections(
        location_label=location_label,
        aoi_description=aoi_description,
        selected_date=selected_date,
        selected_time=selected_time,
        granularity=int(granularity),
        generate_clicked=generate_clicked,
        polygon_aoi=polygon_aoi,
        aoi_error=aoi_error,
    )
